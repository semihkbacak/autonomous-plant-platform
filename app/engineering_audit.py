"""Local simulator HTTP command-attempt ledger, not an OT security audit system."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import threading

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_LOCK = threading.Lock()


def database_path() -> Path:
    raw = os.environ.get('APP_ENGINEERING_AUDIT_DB')
    return Path(raw).expanduser() if raw else (Path.home() / '.local/state/autonomous-plant-platform/local_command_audit.sqlite3')


def _connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=8)
    conn.execute('PRAGMA busy_timeout=8000')
    conn.execute('''CREATE TABLE IF NOT EXISTS command_attempts (
        id INTEGER PRIMARY KEY, utc TEXT NOT NULL, method TEXT NOT NULL,
        route TEXT NOT NULL, status INTEGER NOT NULL, local_client TEXT NOT NULL,
        opt_in_header INTEGER NOT NULL, note TEXT NOT NULL
    )''')
    return conn


def record(method: str, route: str, status: int, local_client: str, header: bool, note: str):
    # No request bodies, credentials, cookies, IP history or personal secrets.
    with _LOCK:
        conn = _connect()
        try:
            conn.execute('INSERT INTO command_attempts (utc, method, route, status, local_client, opt_in_header, note) VALUES (?,?,?,?,?,?,?)',
                         (datetime.now(timezone.utc).isoformat(), method, route, status, local_client, int(header), note))
            conn.commit()
        finally:
            conn.close()


def recent_attempts(limit: int = 40):
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    if not database_path().exists():
        return []
    try:
        with _LOCK:
            conn = _connect()
            try:
                return [dict(zip(('id','utc','method','route','status','local_client','opt_in_header','note'), row))
                        for row in conn.execute('SELECT id,utc,method,route,status,local_client,opt_in_header,note FROM command_attempts ORDER BY id DESC LIMIT ?', (limit,)).fetchall()]
            finally:
                conn.close()
    except sqlite3.DatabaseError:
        return []


class LocalCommandAuditMiddleware(BaseHTTPMiddleware):
    """Opt-in migration gate. Set APP_HARDEN_LEGACY=1 to block old HES mutations.

    Do not interpret as production authentication: a local process can forge
    any confirmation header. Deployment remains strictly loopback only.
    """
    async def dispatch(self, request, call_next):
        path = request.url.path
        method = request.method.upper()
        write = method in ('POST', 'PUT', 'PATCH', 'DELETE')
        if not write or not path.startswith('/api/v1/'):
            return await call_next(request)
        loopback = request.client is not None and request.client.host in ('127.0.0.1', '::1', 'testclient')
        safe = (path.startswith('/api/v1/sim-console/')
                or path == '/api/v1/platform/engineering/portfolio/study')
        local_client = 'LOOPBACK' if loopback else 'NONLOCAL'
        header = request.headers.get('x-sim-console-confirm') == 'SIMULATION_ONLY'
        note = 'HTTP_ATTEMPT_NOT_DEVICE_ACK'
        if os.getenv('APP_HARDEN_LEGACY') == '1' and not safe:
            result = JSONResponse({'detail': 'Legacy mutation routes disabled in hardened local mode; use /api/v1/sim-console/'}, status_code=403)
            status = 403
            note = 'BLOCKED_LEGACY_MUTATION'
        else:
            try:
                result = await call_next(request)
                status = result.status_code
            except Exception:
                status = 500
                note = 'HANDLER_EXCEPTION'
                try:
                    record(method, path, status, local_client, header, note)
                except (OSError, sqlite3.Error):
                    pass
                raise
        try:
            record(method, path, status, local_client, header, note)
        except (OSError, sqlite3.Error):
            # A local demo should still function, but caller must check audit status.
            pass
        return result

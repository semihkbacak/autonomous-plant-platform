"""v1.7 research store: reproducible local SQLite, no field communication."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLANTS = ('HES', 'GES', 'RES')
ID = re.compile(r'^[A-Za-z0-9_-]{1,48}$')
UTC = timezone.utc

def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('UTC timestamp must include timezone offset')
    return dt.astimezone(UTC)

def valid_id(value: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Invalid site or session identifier')
    return value

def valid_power(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Power must be a finite, nonnegative number')
    return float(value)

class ResearchStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, plant TEXT NOT NULL,
                scenario TEXT NOT NULL, step_s INTEGER NOT NULL CHECK(step_s>0),
                start_utc TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'STOPPED',
                created_utc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS samples (
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                step_index INTEGER NOT NULL CHECK(step_index>=0), utc TEXT NOT NULL,
                power_kw REAL NOT NULL CHECK(power_kw>=0), energy_kwh REAL NOT NULL CHECK(energy_kwh>=0),
                PRIMARY KEY(session_id,step_index));
            CREATE TABLE IF NOT EXISTS model_config (
                session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),
                config_json TEXT NOT NULL,
                config_sha256 TEXT NOT NULL CHECK(length(config_sha256)=64));
            CREATE TABLE IF NOT EXISTS measured (
                session_id TEXT NOT NULL, step_index INTEGER NOT NULL,
                measured_kw REAL NOT NULL CHECK(measured_kw>=0),
                PRIMARY KEY(session_id,step_index),
                FOREIGN KEY(session_id,step_index) REFERENCES samples(session_id,step_index));""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        return db

    def bind_model_config(self, session_id: str, config: dict) -> str:
        """Bind the full deterministic screening configuration once per session.

        Cannot retroactively attach a model to manually entered samples. The
        bound digest is checked on every resume even after a process restart.
        Integrity of the SQLite file itself must be protected externally.
        """
        valid_id(session_id)
        canonical = json.dumps(config, sort_keys=True, ensure_ascii=True,
                               separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM sessions WHERE session_id=?', (session_id,)).fetchone() is None:
                raise KeyError('Session not found')
            current = db.execute('SELECT config_sha256,config_json FROM model_config WHERE session_id=?',
                                 (session_id,)).fetchone()
            if current is None:
                count = db.execute('SELECT COUNT(*) FROM samples WHERE session_id=?', (session_id,)).fetchone()[0]
                if count:
                    raise ValueError('Cannot bind model after untracked samples exist')
                db.execute('INSERT INTO model_config VALUES (?,?,?)', (session_id, canonical, digest))
            elif current != (digest, canonical):
                raise ValueError('Simulation model configuration changed; fork a new session')
        return digest

    def backup_verified(self, destination: str | Path) -> dict:
        """Create a consistent SQLite backup and test its structural integrity.

        A backup contains user-supplied research data: keep it local and private.
        """
        target = Path(destination).expanduser().resolve()
        source = self.path.expanduser().resolve()
        if target == source or target.suffix.lower() not in ('.sqlite', '.sqlite3'):
            raise ValueError('Backup target must be a separate .sqlite/.sqlite3 file')
        if target.exists():
            raise FileExistsError('Refusing to overwrite an existing backup')
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.connect() as db:
                with sqlite3.connect(target) as out:
                    db.backup(out)
                    check = out.execute('PRAGMA integrity_check').fetchone()[0]
                    if check != 'ok':
                        raise IOError('SQLite integrity check failed')
            return {'file': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'sqlite_integrity': 'ok', 'site_validated': False}
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @staticmethod
    def restore_verified(source: str | Path, destination: str | Path, expected_sha256: str):
        """Validate a previously exported local research backup before restore.

        Destination must not already exist. No writes to original SQLite DB.
        """
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        if src == dst or dst.exists() or len(expected_sha256) != 64:
            raise ValueError('Invalid restore target or SHA-256')
        if hashlib.sha256(src.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError('Backup SHA-256 mismatch')
        with sqlite3.connect(src.as_uri()+'?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Invalid SQLite backup')
            if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone() is None:
                raise ValueError('Not an Autonomous Plant research backup')
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Exclusive create, avoid silently overwriting a real database.
            with dst.open('xb') as out, src.open('rb') as inp:
                import shutil
                shutil.copyfileobj(inp, out)
            return ResearchStore(dst)
        except Exception:
            dst.unlink(missing_ok=True)
            raise

    def create(self, session_id: str, site_id: str, plant: str, scenario: str,
               start_utc: str, step_s: int = 900):
        valid_id(session_id); valid_id(site_id)
        if plant not in PLANTS: raise ValueError('Unknown synthetic plant type')
        if not isinstance(step_s, int) or isinstance(step_s, bool) or not 1 <= step_s <= 86400:
            raise ValueError('Invalid timestep')
        if not isinstance(scenario, str) or not 1 <= len(scenario) <= 100: raise ValueError('Invalid scenario')
        start = parse_utc(start_utc).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO sessions (session_id,site_id,plant,scenario,step_s,start_utc,created_utc) VALUES(?,?,?,?,?,?,?)',
                       (session_id,site_id,plant,scenario,step_s,start,datetime.now(UTC).isoformat()))
        return self.get(session_id)

    def get(self, session_id: str):
        valid_id(session_id)
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM sessions WHERE session_id=?',(session_id,)).fetchone()
            if row is None: raise KeyError('Session not found')
            s = dict(row)
            data = db.execute('SELECT step_index,utc,power_kw,energy_kwh FROM samples WHERE session_id=? ORDER BY step_index',(session_id,)).fetchall()
        s['samples'] = [dict(x) for x in data]
        s['total_energy_kwh'] = round(sum(x['energy_kwh'] for x in s['samples']),6)
        return s

    def list(self, site_id: str | None=None):
        if site_id is not None:valid_id(site_id)
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            records = db.execute('SELECT session_id,site_id,plant,scenario,status,start_utc FROM sessions WHERE (? IS NULL OR site_id=?) ORDER BY created_utc DESC LIMIT 200', (site_id,site_id)).fetchall()
        return [dict(x) for x in records]

    def add(self, session_id: str, step_index: int, power_kw: float):
        """Atomic sequential write; two concurrent clients cannot append same step."""
        valid_id(session_id)
        power = valid_power(power_kw)
        if type(step_index) is not int or step_index < 0: raise ValueError('Invalid step index')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT start_utc,step_s FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            if row is None: raise KeyError('Session not found')
            expected=db.execute('SELECT COUNT(*) FROM samples WHERE session_id=?', (session_id,)).fetchone()[0]
            if step_index != expected: raise ValueError('Step index must be contiguous')
            dt = parse_utc(row[0]) + timedelta(seconds=row[1] * step_index)
            energy = power * row[1] / 3600
            db.execute('INSERT INTO samples VALUES (?,?,?,?,?)',
                       (session_id,step_index,dt.isoformat(),power,energy))
        return {'step_index':step_index,'utc':dt.isoformat(),'power_kw':power,'energy_kwh':energy}

    def measurements(self, session_id: str, rows: list[dict]):
        s=self.get(session_id)
        if len(rows)>100000:raise ValueError('Too many measurements')
        known={x['step_index'] for x in s['samples']}
        inserted=[]
        for row in rows:
            idx=row['step_index']
            if not isinstance(idx,int) or isinstance(idx,bool) or idx not in known:raise ValueError('Unknown sample step')
            inserted.append((session_id,idx,valid_power(row['measured_kw'])))
        with self.connect() as db:
            db.executemany('INSERT OR REPLACE INTO measured VALUES (?,?,?)',inserted)
        return len(inserted)

    def evaluation(self, session_id: str):
        from research_v2.validation import evaluate_pairs
        self.get(session_id)
        with self.connect() as db:
            rows=db.execute('SELECT s.power_kw,m.measured_kw FROM samples s JOIN measured m ON s.session_id=m.session_id AND s.step_index=m.step_index WHERE s.session_id=? ORDER BY s.step_index',(session_id,)).fetchall()
        return evaluate_pairs(rows)

    @staticmethod
    def _safe_cell(s):
        # CSV/Excel values beginning with formula characters can execute formulas
        # when a user opens the report. Neutralize these without mutating stored data.
        if isinstance(s,str) and s.lstrip().startswith(('=','+','-','@')):
            return "'"+s
        return s

    def export_xlsx(self, session_id: str) -> bytes:
        """Small local research report; requires openpyxl, never stores macros."""
        from io import BytesIO
        from openpyxl import Workbook
        s=self.get(session_id)
        wb=Workbook(); ws=wb.active; ws.title='Synthetic samples'
        ws.append(['session_id','site_id','plant','scenario','step_index','utc','power_kw','energy_kwh'])
        for v in s['samples']:
            ws.append([self._safe_cell(x) for x in (
                s['session_id'],s['site_id'],s['plant'],s['scenario'],v['step_index'],
                v['utc'],v['power_kw'],v['energy_kwh'])])
        wb.create_sheet('Readme')
        wb['Readme'].append(['SIMULATION / RESEARCH ONLY — NOT OEM CERTIFIED'])
        wb['Readme'].append(['Real control authorized',False])
        b=BytesIO();wb.save(b);return b.getvalue()

    def export_csv(self, session_id: str):
        s=self.get(session_id);out=io.StringIO(newline='');w=csv.writer(out,lineterminator='\n')
        w.writerow(['session_id','site_id','plant','scenario','step_index','utc','power_kw','energy_kwh'])
        for v in s['samples']:
            w.writerow([self._safe_cell(x) for x in (s['session_id'],s['site_id'],s['plant'],s['scenario'],v['step_index'],v['utc'],v['power_kw'],v['energy_kwh'])])
        return out.getvalue()

def comparison(st: ResearchStore, ids: list[str]):
    if not 2 <= len(ids) <= 10 or len(set(ids))!=len(ids):raise ValueError('Select 2-10 distinct sessions')
    sessions=[st.get(i) for i in ids]
    return [{'session_id':s['session_id'],'site_id':s['site_id'],'plant':s['plant'],
             'scenario':s['scenario'],'total_energy_kwh':s['total_energy_kwh'],
             'peak_kw':max((x['power_kw'] for x in s['samples']),default=0),
             'sample_count':len(s['samples'])} for s in sessions]

"""RES v0.5: atomic SQLite history for simulator-only 15-minute intervals."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from math import isclose, isfinite, fsum
from pathlib import Path

from simulator.wind_physics import WindInterval

SCHEMA = """
CREATE TABLE IF NOT EXISTS wind_runs (
 id INTEGER PRIMARY KEY, scenario TEXT NOT NULL UNIQUE,
 interval_count INTEGER NOT NULL CHECK(interval_count > 0),
 energy_kwh REAL NOT NULL CHECK(energy_kwh >= 0),
 source_kind TEXT NOT NULL CHECK(source_kind='SYNTHETIC_WIND_SIMULATION_NOT_OEM')
);
CREATE TABLE IF NOT EXISTS wind_intervals (
 run_id INTEGER NOT NULL REFERENCES wind_runs(id) ON DELETE CASCADE,
 end_utc TEXT NOT NULL, available_kw REAL NOT NULL CHECK(available_kw>=0),
 dispatched_kw REAL NOT NULL CHECK(dispatched_kw>=0),
 curtailed_kw REAL NOT NULL CHECK(curtailed_kw>=0),
 interval_kwh REAL NOT NULL CHECK(interval_kwh>=0),
 unserved_kw REAL NOT NULL CHECK(unserved_kw>=0),
 PRIMARY KEY(run_id,end_utc)
);
CREATE TABLE IF NOT EXISTS wind_turbines (
 run_id INTEGER NOT NULL, end_utc TEXT NOT NULL, turbine_id TEXT NOT NULL,
 status TEXT NOT NULL, hub_wind_m_s REAL NOT NULL CHECK(hub_wind_m_s>=0),
 effective_wind_m_s REAL NOT NULL CHECK(effective_wind_m_s>=0),
 wake_loss_fraction REAL NOT NULL CHECK(wake_loss_fraction BETWEEN 0 AND 1),
 available_kw REAL NOT NULL CHECK(available_kw>=0),
 dispatched_kw REAL NOT NULL CHECK(dispatched_kw>=0),
 curtailed_kw REAL NOT NULL CHECK(curtailed_kw>=0),
 rotor_rpm_proxy REAL NOT NULL CHECK(rotor_rpm_proxy>=0),
 high_wind_latched INTEGER NOT NULL CHECK(high_wind_latched IN (0,1)),
 PRIMARY KEY(run_id,end_utc,turbine_id),
 FOREIGN KEY(run_id,end_utc) REFERENCES wind_intervals(run_id,end_utc) ON DELETE CASCADE
);
"""


class WindHistorian:
    def __init__(self, path: str | Path, *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._db() as db:
                db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        if self.read_only:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            if not self.read_only:
                conn.commit()
        except BaseException:
            if not self.read_only:
                conn.rollback()
            raise
        finally:
            conn.close()

    def save_run(self, scenario: str, intervals: list[WindInterval]) -> int:
        if self.read_only:
            raise PermissionError("Historian is read-only")
        if not scenario.strip() or not intervals:
            raise ValueError("Scenario and intervals are required")
        previous = None
        ids = tuple(u.turbine_id for u in intervals[0].turbines)
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Invalid turbine identities")
        cumulative = 0.0
        with self._db() as db:
            run_id = db.execute(
                "INSERT INTO wind_runs(scenario,interval_count,energy_kwh,source_kind) VALUES(?,?,?,?)",
                (scenario, len(intervals), 0.0, "SYNTHETIC_WIND_SIMULATION_NOT_OEM"),
            ).lastrowid
            for interval in intervals:
                stamp = interval.end_utc
                if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
                    raise ValueError("UTC timestamp required")
                if previous is not None and stamp - previous != timedelta(minutes=15):
                    raise ValueError("Noncontiguous wind intervals")
                previous = stamp
                if interval.source_kind != "SYNTHETIC_WIND_SIMULATION_NOT_OEM":
                    raise ValueError("Invalid provenance")
                if tuple(u.turbine_id for u in interval.turbines) != ids:
                    raise ValueError("Turbine identities changed")
                vals = (
                    interval.farm_available_kw, interval.farm_dispatched_kw,
                    interval.farm_curtailed_kw, interval.energy_kwh, interval.unserved_target_kw,
                )
                if not all(isfinite(x) and x >= 0 for x in vals):
                    raise ValueError("Invalid farm telemetry")
                if not (
                    isclose(interval.energy_kwh, interval.farm_dispatched_kw / 4, abs_tol=1e-6)
                    and isclose(interval.farm_available_kw, interval.farm_dispatched_kw + interval.farm_curtailed_kw, abs_tol=1e-6)
                    and isclose(interval.farm_dispatched_kw, fsum(u.dispatched_kw for u in interval.turbines), abs_tol=1e-6)
                ):
                    raise ValueError("Farm energy or dispatch mismatch")
                cumulative += interval.energy_kwh
                iso = stamp.isoformat()
                db.execute(
                    "INSERT INTO wind_intervals VALUES(?,?,?,?,?,?,?)",
                    (run_id, iso, *vals),
                )
                for u in interval.turbines:
                    v = (
                        u.hub_wind_m_s, u.effective_wind_m_s, u.wake_loss_fraction,
                        u.available_kw, u.dispatched_kw, u.curtailed_kw, u.rotor_rpm_proxy,
                    )
                    if not all(isfinite(n) and n >= 0 for n in v) or not 0 <= u.wake_loss_fraction <= 1:
                        raise ValueError("Invalid turbine telemetry")
                    db.execute(
                        "INSERT INTO wind_turbines VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, iso, u.turbine_id, u.status, *v, int(u.high_wind_latched)),
                    )
            db.execute("UPDATE wind_runs SET energy_kwh=? WHERE id=?", (cumulative, run_id))
        return int(run_id)

    def runs(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM wind_runs ORDER BY id DESC")]

    def intervals(self, run_id: int) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM wind_intervals WHERE run_id=? ORDER BY end_utc", (run_id,)
            )]

    def turbines(self, run_id: int) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM wind_turbines WHERE run_id=? ORDER BY end_utc,turbine_id", (run_id,)
            )]

    def audit(self, expected: set[str] | None = None) -> dict:
        issues = []
        with self._db() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                issues.append("SQLITE_INTEGRITY")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                issues.append("FOREIGN_KEYS")
            runs = db.execute("SELECT * FROM wind_runs").fetchall()
            if expected is not None and {r['scenario'] for r in runs} != expected:
                issues.append("SCENARIO_COVERAGE")
            for r in runs:
                ri = r['id']
                samples = db.execute(
                    "SELECT * FROM wind_intervals WHERE run_id=? ORDER BY end_utc", (ri,)
                ).fetchall()
                turbines = db.execute(
                    "SELECT * FROM wind_turbines WHERE run_id=?", (ri,)
                ).fetchall()
                if len(samples) != r['interval_count'] or len(turbines) != 2 * len(samples):
                    issues.append(f"ROW_COUNTS:{r['scenario']}")
                total = fsum(x['interval_kwh'] for x in samples)
                if not isclose(total, r['energy_kwh'], rel_tol=0, abs_tol=1e-6):
                    issues.append(f"ENERGY:{r['scenario']}")
                prev = None
                for x in samples:
                    stamp = datetime.fromisoformat(x['end_utc'])
                    if (stamp.tzinfo is None or stamp.utcoffset() != timedelta(0)
                        or (prev is not None and stamp - prev != timedelta(minutes=15))):
                        issues.append(f"TIMELINE:{r['scenario']}")
                    prev = stamp
                    if not (
                        isclose(x['interval_kwh'], x['dispatched_kw'] / 4, abs_tol=1e-6)
                        and isclose(x['available_kw'], x['dispatched_kw'] + x['curtailed_kw'], abs_tol=1e-6)
                    ):
                        issues.append(f"DISPATCH:{r['scenario']}")
                by_interval = {}
                for u in turbines:
                    key = u['end_utc']
                    s = by_interval.setdefault(key, [0.0, 0.0, 0])
                    s[0] += u['available_kw']
                    s[1] += u['dispatched_kw']
                    s[2] += 1
                for x in samples:
                    s = by_interval.get(x['end_utc'], [0,0,0])
                    if s[2] != 2 or not (
                        isclose(s[0], x['available_kw'], abs_tol=1e-6)
                        and isclose(s[1], x['dispatched_kw'], abs_tol=1e-6)
                    ):
                        issues.append(f"TURBINE_TOTALS:{r['scenario']}")
        return {'passed': not issues, 'issues': issues, 'run_count': len(runs),
                'source': 'SYNTHETIC_NOT_FIELD_VALIDATED'}

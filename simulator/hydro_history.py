"""HES simulator-only SQLite Historian and analytics.

Energy integration uses sampled power * elapsed simulation time.
The model is synthetic and not field-calibrated.
"""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.alarms import detect_alarms
from core.models import PlantState


def _finite(value, *, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("HES telemetry must be numeric")
    value = float(value)
    if not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError("HES telemetry nonfinite or negative")
    return value


class HydroHistorian:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS hydro_runs (
                    id INTEGER PRIMARY KEY,
                    scenario TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    sample_count INTEGER NOT NULL CHECK(sample_count >= 2),
                    duration_s REAL NOT NULL CHECK(duration_s > 0),
                    energy_mwh REAL NOT NULL CHECK(energy_mwh >= 0),
                    source_kind TEXT NOT NULL
                        CHECK(source_kind='SYNTHETIC_DYNAMIC_1S')
                );

                CREATE TABLE IF NOT EXISTS hydro_samples (
                    run_id INTEGER NOT NULL
                        REFERENCES hydro_runs(id) ON DELETE CASCADE,
                    simulation_time_s REAL NOT NULL,
                    power_mw REAL NOT NULL CHECK(power_mw >= 0),
                    increment_mwh REAL NOT NULL CHECK(increment_mwh >= 0),
                    cumulative_mwh REAL NOT NULL CHECK(cumulative_mwh >= 0),
                    net_head_m REAL NOT NULL CHECK(net_head_m >= 0),
                    headpond_level_pct REAL NOT NULL
                        CHECK(headpond_level_pct BETWEEN 0 AND 100),
                    grid_available INTEGER NOT NULL
                        CHECK(grid_available IN (0,1)),
                    emergency_stop INTEGER NOT NULL
                        CHECK(emergency_stop IN (0,1)),
                    maintenance_lock INTEGER NOT NULL
                        CHECK(maintenance_lock IN (0,1)),
                    PRIMARY KEY(run_id, simulation_time_s)
                );

                CREATE TABLE IF NOT EXISTS hydro_units (
                    run_id INTEGER NOT NULL,
                    simulation_time_s REAL NOT NULL,
                    unit_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    power_mw REAL NOT NULL CHECK(power_mw >= 0),
                    flow_m3_s REAL NOT NULL CHECK(flow_m3_s >= 0),
                    rpm REAL NOT NULL CHECK(rpm >= 0),
                    bearing_temperature_c REAL NOT NULL,
                    generator_temperature_c REAL NOT NULL,
                    vibration_mm_s REAL NOT NULL CHECK(vibration_mm_s >= 0),
                    needle_opening_pct REAL NOT NULL
                        CHECK(needle_opening_pct BETWEEN 0 AND 100),
                    target_power_mw REAL NOT NULL
                        CHECK(target_power_mw >= 0),
                    increment_mwh REAL NOT NULL
                        CHECK(increment_mwh >= 0),
                    PRIMARY KEY(run_id, simulation_time_s, unit_id),
                    FOREIGN KEY(run_id, simulation_time_s)
                        REFERENCES hydro_samples(run_id, simulation_time_s)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS hydro_alarms (
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER NOT NULL
                        REFERENCES hydro_runs(id) ON DELETE CASCADE,
                    simulation_time_s REAL NOT NULL,
                    code TEXT NOT NULL,
                    unit_id TEXT,
                    severity TEXT NOT NULL,
                    transition TEXT NOT NULL
                        CHECK(transition IN ('RAISED','CLEARED'))
                );

                CREATE INDEX IF NOT EXISTS ix_hydro_alarms_run
                    ON hydro_alarms(run_id, simulation_time_s);
            """)

    @classmethod
    def for_reading(cls, db_path: str | Path):
        """Open existing data without creating or changing database tables."""
        result = cls.__new__(cls)
        result.path = Path(db_path)
        return result

    @contextmanager
    def _connect(self, *, read_only=False):
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(self.path)
            db = sqlite3.connect(
                self.path.resolve().as_uri() + "?mode=ro",
                uri=True, timeout=30,
            )
        else:
            db = sqlite3.connect(self.path, timeout=30)

        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            if not read_only:
                db.commit()
        except BaseException:
            if not read_only:
                db.rollback()
            raise
        finally:
            db.close()

    def save_run(self, scenario: str, snapshots: list[PlantState]) -> int:
        """Save the complete run atomically."""
        if not isinstance(scenario, str) or not scenario.strip():
            raise ValueError("Scenario name required")
        if len(snapshots) < 2:
            raise ValueError("Need two or more HES snapshots")

        unit_ids = tuple(u.unit_id for u in snapshots[0].units)
        if not unit_ids or len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Invalid HES unit identities")

        start = _finite(snapshots[0].simulation_time_s)
        previous = None
        cumulative = 0.0
        active = {}

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute(
                "INSERT INTO hydro_runs "
                "(scenario,recorded_at_utc,sample_count,duration_s,"
                "energy_mwh,source_kind) VALUES(?,?,?,?,?,?)",
                (
                    scenario.strip(),
                    datetime.now(timezone.utc).isoformat(),
                    len(snapshots),
                    1.0,
                    0.0,
                    "SYNTHETIC_DYNAMIC_1S",
                ),
            )
            run_id = int(cur.lastrowid)

            for state in snapshots:
                t = _finite(state.simulation_time_s)
                if previous is not None and t <= previous:
                    raise ValueError(
                        "Non-monotonic HES simulation timestamps"
                    )
                if tuple(u.unit_id for u in state.units) != unit_ids:
                    raise ValueError(
                        "HES unit identities changed within run"
                    )

                dt = 0.0 if previous is None else t - previous
                power = sum(
                    _finite(u.active_power_mw) for u in state.units
                )
                delta = power * dt / 3600.0
                cumulative += delta

                net_head = _finite(state.net_head_m)
                level = _finite(state.headpond_level_pct)
                if level > 100:
                    raise ValueError("Invalid headpond level")

                db.execute("""
                    INSERT INTO hydro_samples
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                """, (
                    run_id, t, power, delta, cumulative,
                    net_head, level,
                    int(state.grid_available),
                    int(state.emergency_stop),
                    int(state.maintenance_lock),
                ))

                for unit in state.units:
                    values = (
                        _finite(unit.flow_m3_s),
                        _finite(unit.rpm),
                        _finite(
                            unit.bearing_temperature_c,
                            nonnegative=False,
                        ),
                        _finite(
                            unit.generator_temperature_c,
                            nonnegative=False,
                        ),
                        _finite(unit.vibration_mm_s),
                        _finite(unit.needle_opening_pct),
                        _finite(unit.governor_target_power_mw),
                    )

                    if values[5] > 100:
                        raise ValueError(
                            "Invalid Pelton needle position"
                        )

                    db.execute("""
                        INSERT INTO hydro_units
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        run_id,
                        t,
                        unit.unit_id,
                        unit.status.value,
                        _finite(unit.active_power_mw),
                        *values,
                        _finite(unit.active_power_mw) * dt / 3600.0,
                    ))

                current = {
                    (a.code, a.unit_id): a.severity.value
                    for a in detect_alarms(state)
                }

                for (code, uid), severity in current.items():
                    if (code, uid) not in active:
                        db.execute(
                            "INSERT INTO hydro_alarms "
                            "(run_id,simulation_time_s,code,unit_id,"
                            "severity,transition) VALUES(?,?,?,?,?,?)",
                            (run_id, t, code, uid, severity, "RAISED"),
                        )

                for (code, uid), severity in active.items():
                    if (code, uid) not in current:
                        db.execute(
                            "INSERT INTO hydro_alarms "
                            "(run_id,simulation_time_s,code,unit_id,"
                            "severity,transition) VALUES(?,?,?,?,?,?)",
                            (run_id, t, code, uid, severity, "CLEARED"),
                        )

                active = current
                previous = t

            duration = previous - start
            if duration <= 0:
                raise ValueError("Zero duration")

            db.execute(
                "UPDATE hydro_runs SET duration_s=?,energy_mwh=? "
                "WHERE id=?",
                (duration, cumulative, run_id),
            )

        return run_id

    def runs(self) -> list[dict]:
        with self._connect(read_only=True) as db:
            return [
                dict(r) for r in db.execute(
                    "SELECT * FROM hydro_runs ORDER BY id DESC"
                )
            ]

    def samples(self, run_id: int) -> list[dict]:
        with self._connect(read_only=True) as db:
            return [
                dict(r) for r in db.execute(
                    "SELECT * FROM hydro_samples WHERE run_id=? "
                    "ORDER BY simulation_time_s",
                    (run_id,),
                )
            ]

    def units(self, run_id: int) -> list[dict]:
        with self._connect(read_only=True) as db:
            return [
                dict(r) for r in db.execute(
                    "SELECT * FROM hydro_units WHERE run_id=? "
                    "ORDER BY simulation_time_s,unit_id",
                    (run_id,),
                )
            ]

    def alarms(self, run_id: int) -> list[dict]:
        with self._connect(read_only=True) as db:
            return [
                dict(r) for r in db.execute(
                    "SELECT simulation_time_s,code,unit_id,severity,"
                    "transition FROM hydro_alarms "
                    "WHERE run_id=? ORDER BY simulation_time_s,id",
                    (run_id,),
                )
            ]

    def summary(self, run_id: int) -> dict:
        with self._connect(read_only=True) as db:
            run = db.execute(
                "SELECT * FROM hydro_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)

            stats = db.execute("""
                SELECT
                    MAX(power_mw) peak_mw,
                    AVG(power_mw) mean_mw,
                    MIN(net_head_m) min_net_head_m,
                    SUM(increment_mwh) summed_energy_mwh
                FROM hydro_samples WHERE run_id=?
            """, (run_id,)).fetchone()

            by_unit = [
                dict(r) for r in db.execute("""
                    SELECT
                        unit_id,
                        SUM(increment_mwh) energy_mwh,
                        MAX(power_mw) peak_mw,
                        AVG(flow_m3_s) avg_flow_m3_s,
                        MAX(vibration_mm_s) max_vibration_mm_s,
                        AVG(
                            CASE
                                WHEN status='RUNNING'
                                AND target_power_mw>0
                                THEN ABS(power_mw-target_power_mw)
                            END
                        ) governor_mae_mw
                    FROM hydro_units
                    WHERE run_id=?
                    GROUP BY unit_id
                    ORDER BY unit_id
                """, (run_id,))
            ]

            events = db.execute(
                "SELECT COUNT(*) FROM hydro_alarms "
                "WHERE run_id=? AND transition='RAISED'",
                (run_id,),
            ).fetchone()[0]

            return {
                **dict(run),
                **dict(stats),
                "unit_metrics": by_unit,
                "alarm_raises": events,
                "scope": "SYNTHETIC_1S_DYNAMIC_SAMPLED",
            }

    def audit(self, expected_cases: set[str] | None = None) -> dict:
        issues = []

        with self._connect(read_only=True) as db:
            if db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0] != "ok":
                issues.append("SQLITE_INTEGRITY")

            if db.execute(
                "PRAGMA foreign_key_check"
            ).fetchall():
                issues.append("FOREIGN_KEYS")

            runs = db.execute(
                "SELECT id,scenario,sample_count,energy_mwh,duration_s "
                "FROM hydro_runs"
            ).fetchall()

            names = [r["scenario"] for r in runs]

            if len(names) != len(set(names)):
                issues.append("DUPLICATE_CASES")
            if expected_cases is not None and set(names) != expected_cases:
                issues.append("SCENARIO_COVERAGE")

            for r in runs:
                samples = db.execute(
                    "SELECT simulation_time_s,increment_mwh,"
                    "cumulative_mwh FROM hydro_samples "
                    "WHERE run_id=? ORDER BY simulation_time_s",
                    (r["id"],),
                ).fetchall()

                units = db.execute(
                    "SELECT simulation_time_s,increment_mwh "
                    "FROM hydro_units WHERE run_id=?",
                    (r["id"],),
                ).fetchall()

                if (
                    len(samples) != r["sample_count"]
                    or len(units) != len(samples) * 2
                ):
                    issues.append(
                        "SAMPLE_COUNTS:" + r["scenario"]
                    )

                if not samples:
                    continue

                total = math.fsum(
                    x["increment_mwh"] for x in samples
                )
                unit_total = math.fsum(
                    x["increment_mwh"] for x in units
                )

                if any(
                    not math.isfinite(x["increment_mwh"])
                    for x in samples
                ) or not (
                    math.isclose(
                        total, r["energy_mwh"], abs_tol=1e-7
                    )
                    and math.isclose(
                        total, unit_total, abs_tol=1e-7
                    )
                    and math.isclose(
                        total,
                        samples[-1]["cumulative_mwh"],
                        abs_tol=1e-7,
                    )
                    and math.isclose(
                        samples[-1]["simulation_time_s"]
                        - samples[0]["simulation_time_s"],
                        r["duration_s"],
                        abs_tol=1e-8,
                    )
                ):
                    issues.append(
                        "ENERGY_OR_TIMELINE:" + r["scenario"]
                    )

        return {
            "passed": not issues,
            "issues": issues,
            "run_count": len(runs),
            "scope": (
                "SIMULATION_DATABASE_NOT_OEM_OR_FIELD_VALIDATION"
            ),
        }
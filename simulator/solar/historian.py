
from __future__ import annotations

import json
import sqlite3

from contextlib import contextmanager
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from simulator.solar.inverter_history_adapter import (
    append_simulated_inverter_interval,
)

from simulator.solar.inverter_history_schema import (
    initialize_ges_inverter_schema,
)

from simulator.solar.inverter_history_writer import (
    register_parameter_snapshot,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)

from simulator.solar.mppt_history import (
    initialize_mppt_schema,
    append_mppt_interval,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
)


class SolarHistorian:
    """
    Store local simulated GES plant and inverter
    history in SQLite.

    Tables:
    - simulation_runs
    - production_intervals
    - alarm_events
    - ges_parameter_snapshots
    - ges_inverter_intervals
    - ges_inverter_alarm_events

    Simulation only. No PLC, SCADA or OT control.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._create_schema()

    # ========================================================
    # SQLITE CONNECTION
    # ========================================================

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(
            self.db_path,
            timeout=30,
        )

        db.row_factory = sqlite3.Row

        db.execute(
            "PRAGMA foreign_keys = ON"
        )

        try:
            with db:
                yield db
        finally:
            db.close()

    # ========================================================
    # DATABASE SCHEMA
    # ========================================================

    def _create_schema(self) -> None:
        with self._connect() as db:

            db.execute("BEGIN IMMEDIATE")

            db.execute("""
                CREATE TABLE IF NOT EXISTS simulation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    scenario TEXT NOT NULL,

                    created_at_utc TEXT NOT NULL,

                    interval_count INTEGER NOT NULL
                        CHECK (interval_count > 0),

                    total_energy_kwh REAL NOT NULL
                        CHECK (total_energy_kwh >= 0)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS production_intervals (
                    run_id INTEGER NOT NULL
                        REFERENCES simulation_runs(id)
                        ON DELETE CASCADE,

                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,

                    available_power_kw REAL NOT NULL
                        CHECK (available_power_kw >= 0),

                    dispatched_power_kw REAL NOT NULL
                        CHECK (dispatched_power_kw >= 0),

                    interval_energy_kwh REAL NOT NULL
                        CHECK (interval_energy_kwh >= 0),

                    cumulative_energy_kwh REAL NOT NULL
                        CHECK (cumulative_energy_kwh >= 0),

                    curtailed_power_kw REAL NOT NULL
                        CHECK (curtailed_power_kw >= 0),

                    unserved_target_kw REAL NOT NULL
                        CHECK (unserved_target_kw >= 0),

                    reasons_json TEXT NOT NULL,
                    quality_flags_json TEXT NOT NULL,
                    source_types_json TEXT NOT NULL,
                    active_alarms_json TEXT NOT NULL,

                    PRIMARY KEY (run_id, start_utc)
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS alarm_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    run_id INTEGER NOT NULL
                        REFERENCES simulation_runs(id)
                        ON DELETE CASCADE,

                    detected_at_utc TEXT NOT NULL,

                    code TEXT NOT NULL,

                    inverter_id TEXT,

                    transition TEXT NOT NULL
                        CHECK (
                            transition IN (
                                'RAISED',
                                'CLEARED'
                            )
                        )
                )
            """)

            initialize_ges_inverter_schema(db)
            initialize_mppt_schema(db)

    # ========================================================
    # SAVE SIMULATION
    # ========================================================

    def save_simulation(
        self,
        simulator: SolarTimeSeriesSimulator,
        scenario: str = "NORMAL",
        *,
        inverter_snapshot_payloads: (
            dict[str, dict] | None
        ) = None,
    ) -> int:

        # ----------------------------------------------------
        # VALIDATE SIMULATION
        # ----------------------------------------------------

        if (
            not isinstance(scenario, str)
            or not scenario.strip()
        ):
            raise ValueError(
                "Scenario cannot be empty"
            )

        if not simulator.records:
            raise ValueError(
                "No simulation records to save"
            )

        for record in simulator.records:

            values = (
                record.available_power_kw,
                record.dispatched_power_kw,
                record.interval_energy_kwh,
                record.cumulative_energy_kwh,
                record.curtailed_power_kw,
                record.unserved_target_kw,
            )

            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
                for value in values
            ):
                raise ValueError(
                    "Invalid numeric production record"
                )

        # ----------------------------------------------------
        # VALIDATE INVERTER IDENTITIES
        # ----------------------------------------------------

        expected_inverter_ids: tuple[str, ...] = ()

        if inverter_snapshot_payloads is not None:

            if not isinstance(
                inverter_snapshot_payloads,
                dict,
            ):
                raise ValueError(
                    "Invalid inverter snapshot payload mapping"
                )

            expected_inverter_ids = tuple(
                item.inverter_id
                for item
                in simulator.records[0].inverter_results
            )

            if (
                not expected_inverter_ids
                or len(expected_inverter_ids)
                != len(set(expected_inverter_ids))
                or set(inverter_snapshot_payloads)
                != set(expected_inverter_ids)
            ):
                raise ValueError(
                    "Inverter snapshot/configuration mismatch"
                )

            for record in simulator.records:

                record_ids = tuple(
                    item.inverter_id
                    for item in record.inverter_results
                )

                if record_ids != expected_inverter_ids:
                    raise ValueError(
                        "Inverter set changed across intervals"
                    )

        # ----------------------------------------------------
        # ATOMIC DATABASE TRANSACTION
        # ----------------------------------------------------

        with self._connect() as db:

            # -----------------------------------------------
            # CREATE SIMULATION RUN
            # -----------------------------------------------

            cursor = db.execute("""
                INSERT INTO simulation_runs (
                    scenario,
                    created_at_utc,
                    interval_count,
                    total_energy_kwh
                )
                VALUES (?, ?, ?, ?)
            """, (
                scenario.strip(),
                datetime.now(
                    timezone.utc
                ).isoformat(),
                len(simulator.records),
                simulator.records[
                    -1
                ].cumulative_energy_kwh,
            ))

            run_id = int(cursor.lastrowid)

            # -----------------------------------------------
            # REGISTER PARAMETER SNAPSHOTS
            # -----------------------------------------------

            parameter_snapshot_ids: dict[str, str] = {}

            if inverter_snapshot_payloads is not None:

                for inverter_id in expected_inverter_ids:

                    payload = (
                        inverter_snapshot_payloads[
                            inverter_id
                        ]
                    )

                    if (
                        not isinstance(payload, dict)
                        or payload.get("component_id")
                        != inverter_id
                    ):
                        raise ValueError(
                            "Snapshot component ID mismatch"
                        )

                    parameter_snapshot_ids[inverter_id] = (
                        register_parameter_snapshot(
                            db,
                            payload,
                        )
                    )

            # -----------------------------------------------
            # SAVE PLANT + INVERTER INTERVALS
            # -----------------------------------------------

            for record in simulator.records:

                db.execute("""
                    INSERT INTO production_intervals (
                        run_id,
                        start_utc,
                        end_utc,
                        available_power_kw,
                        dispatched_power_kw,
                        interval_energy_kwh,
                        cumulative_energy_kwh,
                        curtailed_power_kw,
                        unserved_target_kw,
                        reasons_json,
                        quality_flags_json,
                        source_types_json,
                        active_alarms_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    record.start_utc.isoformat(),
                    record.end_utc.isoformat(),
                    record.available_power_kw,
                    record.dispatched_power_kw,
                    record.interval_energy_kwh,
                    record.cumulative_energy_kwh,
                    record.curtailed_power_kw,
                    record.unserved_target_kw,
                    json.dumps(record.reasons),
                    json.dumps(record.quality_flags),
                    json.dumps(record.source_types),
                    json.dumps(record.active_alarms),
                ))

                # Inverter history in same transaction.

                if inverter_snapshot_payloads is not None:

                    append_simulated_inverter_interval(
                        db,
                        run_id=run_id,
                        record=record,
                        expected_inverter_ids=(
                            expected_inverter_ids
                        ),
                        parameter_snapshot_ids=(
                            parameter_snapshot_ids
                        ),
                    )

                # Integrated GES requires MPPT reports.
                # Legacy GES may omit them.

                append_mppt_interval(
                    db,
                    run_id,
                    record,
                    require_mppt_reports=isinstance(
                        simulator.pipeline,
                        IntegratedSolarPhysicsPipeline,
                    ),
                )

            # -----------------------------------------------
            # SAVE PLANT ALARM TRANSITIONS
            # -----------------------------------------------

            for event in simulator.alarm_history:

                db.execute("""
                    INSERT INTO alarm_events (
                        run_id,
                        detected_at_utc,
                        code,
                        inverter_id,
                        transition
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    run_id,
                    event.timestamp_utc.isoformat(),
                    event.code,
                    event.inverter_id,
                    event.transition,
                ))

        return run_id

    # ========================================================
    # READ SIMULATION RUNS
    # ========================================================

    def list_runs(self) -> list[dict]:

        with self._connect() as db:

            rows = db.execute("""
                SELECT *
                FROM simulation_runs
                ORDER BY id DESC
            """).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    # ========================================================
    # READ PRODUCTION INTERVALS
    # ========================================================

    def get_intervals(
        self,
        run_id: int,
    ) -> list[dict]:

        with self._connect() as db:

            rows = db.execute("""
                SELECT *
                FROM production_intervals
                WHERE run_id = ?
                ORDER BY start_utc
            """, (
                run_id,
            )).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    # ========================================================
    # READ ALARM HISTORY
    # ========================================================

    def get_alarms(
        self,
        run_id: int,
    ) -> list[dict]:

        with self._connect() as db:

            rows = db.execute("""
                SELECT *
                FROM alarm_events
                WHERE run_id = ?
                ORDER BY id
            """, (
                run_id,
            )).fetchall()

        return [
            dict(row)
            for row in rows
        ]

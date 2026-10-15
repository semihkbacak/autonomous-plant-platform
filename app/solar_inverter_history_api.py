
from __future__ import annotations

import json
import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse


def create_solar_inverter_history_router(
    db_path: str | Path,
) -> APIRouter:

    database = Path(db_path).expanduser().resolve()

    router = APIRouter(
        prefix="/solar/inverters",
        tags=["GES Inverters (read-only)"],
    )

    @contextmanager
    def open_db() -> Iterator[sqlite3.Connection]:

        if not database.is_file():
            raise HTTPException(
                503,
                "GES Historian veritabani bulunamadi",
            )

        try:
            db = sqlite3.connect(
                database.as_uri() + "?mode=ro",
                uri=True,
                timeout=5,
            )
        except sqlite3.Error as exc:
            raise HTTPException(
                503,
                "GES Historian okunamiyor",
            ) from exc

        db.row_factory = sqlite3.Row

        try:
            yield db
        finally:
            db.close()

    def rows(
        db: sqlite3.Connection,
        sql: str,
        params: tuple = (),
    ) -> list[dict]:

        try:
            return [
                dict(row)
                for row in db.execute(
                    sql,
                    params,
                ).fetchall()
            ]
        except sqlite3.Error as exc:
            raise HTTPException(
                503,
                "GES inverter tablolari okunamiyor",
            ) from exc

    def ensure_run(
        db: sqlite3.Connection,
        run_id: int,
    ) -> None:

        result = rows(
            db,
            "SELECT id FROM simulation_runs WHERE id=?",
            (run_id,),
        )

        if not result:
            raise HTTPException(
                404,
                "Simulasyon kaydi bulunamadi",
            )

    # ========================================================
    # LIST SIMULATION RUNS
    # ========================================================

    @router.get("/runs")
    def list_runs() -> list[dict]:

        with open_db() as db:
            return rows(
                db,
                """
                SELECT
                    r.id,
                    r.scenario,
                    r.created_at_utc,
                    r.interval_count,
                    r.total_energy_kwh,

                    (
                        SELECT COUNT(*)
                        FROM ges_inverter_intervals i
                        WHERE i.run_id = r.id
                    ) AS inverter_record_count

                FROM simulation_runs r
                ORDER BY r.id DESC
                """,
            )

    # ========================================================
    # INVERTER INTERVAL HISTORY
    # ========================================================

    @router.get("/runs/{run_id}/intervals")
    def get_inverter_intervals(
        run_id: int,
        inverter_id: str | None = None,
        limit: int = Query(
            default=1000,
            ge=1,
            le=1000,
        ),
        offset: int = Query(
            default=0,
            ge=0,
        ),
    ) -> list[dict]:

        with open_db() as db:

            ensure_run(db, run_id)

            result = rows(
                db,
                """
                SELECT *
                FROM ges_inverter_intervals
                WHERE run_id = ?
                  AND (
                      ? IS NULL
                      OR inverter_id = ?
                  )
                ORDER BY start_utc, inverter_id
                LIMIT ? OFFSET ?
                """,
                (
                    run_id,
                    inverter_id,
                    inverter_id,
                    limit,
                    offset,
                ),
            )

        for item in result:

            for field in (
                "active_alarms",
                "reasons",
                "quality_flags",
                "source_types",
            ):

                item[field] = json.loads(
                    item.pop(field + "_json")
                )

        return result

    # ========================================================
    # PLANT AND INVERTER ALARMS
    # ========================================================

    @router.get("/runs/{run_id}/alarms")
    def get_inverter_alarms(
        run_id: int,
        inverter_id: str | None = None,
    ) -> list[dict]:

        with open_db() as db:

            ensure_run(db, run_id)

            plant = rows(
                db,
                """
                SELECT
                    detected_at_utc AS timestamp_utc,
                    code,
                    inverter_id,
                    transition
                FROM alarm_events
                WHERE run_id = ?
                ORDER BY detected_at_utc, id
                """,
                (run_id,),
            )

            device = rows(
                db,
                """
                SELECT
                    timestamp_utc,
                    code,
                    inverter_id,
                    transition,
                    time_semantics
                FROM ges_inverter_alarm_events
                WHERE run_id = ?
                  AND (
                      ? IS NULL
                      OR inverter_id = ?
                  )
                ORDER BY
                    timestamp_utc,
                    inverter_id,
                    code
                """,
                (
                    run_id,
                    inverter_id,
                    inverter_id,
                ),
            )

        for item in plant:
            item["source_table"] = "alarm_events"
            item["time_semantics"] = (
                "detected_transition"
            )

        for item in device:
            item["source_table"] = (
                "ges_inverter_alarm_events"
            )

        return sorted(
            plant + device,
            key=lambda item: (
                item["timestamp_utc"],
                item["source_table"],
            ),
        )

    # ========================================================
    # PARAMETER SNAPSHOTS
    # ========================================================

    @router.get("/runs/{run_id}/snapshots")
    def get_snapshots(
        run_id: int,
    ) -> list[dict]:

        with open_db() as db:

            ensure_run(db, run_id)

            result = rows(
                db,
                """
                SELECT DISTINCT
                    s.snapshot_id,
                    s.component_id,
                    s.model_id,
                    s.payload_json

                FROM ges_parameter_snapshots s

                INNER JOIN ges_inverter_intervals i
                    ON i.parameter_snapshot_id =
                       s.snapshot_id

                WHERE i.run_id = ?
                ORDER BY s.component_id
                """,
                (run_id,),
            )

        for item in result:
            item["payload"] = json.loads(
                item.pop("payload_json")
            )

        return result

    # ========================================================
    # READ-ONLY INVERTER DASHBOARD
    # ========================================================

    @router.get(
        "/dashboard",
        include_in_schema=False,
    )
    def get_inverter_dashboard() -> FileResponse:

        dashboard = (
            Path(__file__).resolve().parent
            / "static"
            / "solar_inverter_dashboard.html"
        )

        return FileResponse(
            dashboard,
            media_type="text/html",
        )

    return router

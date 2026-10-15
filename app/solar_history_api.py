
from __future__ import annotations

import json
import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query


def create_solar_history_router(
    db_path: str | Path,
) -> APIRouter:
    """
    Read-only HTTP API for GES Historian.

    No PLC, SCADA or inverter command execution.
    """

    database = Path(db_path).expanduser().resolve()

    router = APIRouter(
        prefix="/solar/history",
        tags=["GES Historian (read-only)"],
    )

    # ------------------------------------------
    # READ-ONLY DATABASE CONNECTION
    # ------------------------------------------

    @contextmanager
    def open_db() -> Iterator[sqlite3.Connection]:

        if not database.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "GES Historian database not found. "
                    "Run the GES demo first."
                ),
            )

        try:
            db = sqlite3.connect(
                database.as_uri() + "?mode=ro",
                uri=True,
            )

        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=503,
                detail="GES Historian database cannot be opened.",
            ) from exc

        db.row_factory = sqlite3.Row

        try:
            yield db
        finally:
            db.close()

    # ------------------------------------------
    # CHECK SIMULATION RUN
    # ------------------------------------------

    def ensure_run(
        db: sqlite3.Connection,
        run_id: int,
    ) -> None:

        exists = db.execute(
            "SELECT 1 FROM simulation_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

        if exists is None:
            raise HTTPException(
                status_code=404,
                detail="Simulation run not found",
            )

    # ------------------------------------------
    # LIST ALL RUNS
    # ------------------------------------------

    @router.get("/runs")
    def list_runs() -> list[dict]:

        with open_db() as db:
            rows = db.execute("""
                SELECT
                    id,
                    scenario,
                    created_at_utc,
                    interval_count,
                    total_energy_kwh
                FROM simulation_runs
                ORDER BY id DESC
            """).fetchall()

            return [dict(row) for row in rows]

    # ------------------------------------------
    # READ PRODUCTION INTERVALS
    # ------------------------------------------

    @router.get("/runs/{run_id}/intervals")
    def get_intervals(
        run_id: int,
        limit: int = Query(
            default=100,
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

            rows = db.execute("""
                SELECT *
                FROM production_intervals
                WHERE run_id = ?
                ORDER BY start_utc
                LIMIT ? OFFSET ?
            """, (
                run_id,
                limit,
                offset,
            )).fetchall()

        result = []

        for row in rows:

            record = dict(row)

            # Convert stored JSON text into
            # structured API arrays.
            for field in (
                "reasons",
                "quality_flags",
                "source_types",
                "active_alarms",
            ):
                record[field] = json.loads(
                    record.pop(field + "_json")
                )

            result.append(record)

        return result

    # ------------------------------------------
    # READ ALARM HISTORY
    # ------------------------------------------

    @router.get("/runs/{run_id}/alarms")
    def get_alarms(
        run_id: int,
        limit: int = Query(
            default=100,
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

            rows = db.execute("""
                SELECT
                    id,
                    run_id,
                    detected_at_utc,
                    code,
                    inverter_id,
                    transition
                FROM alarm_events
                WHERE run_id = ?
                ORDER BY id
                LIMIT ? OFFSET ?
            """, (
                run_id,
                limit,
                offset,
            )).fetchall()

            return [dict(row) for row in rows]

    return router

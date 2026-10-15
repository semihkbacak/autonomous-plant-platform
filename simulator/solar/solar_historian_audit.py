
from __future__ import annotations

import json
import math
import sqlite3

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class SolarRunAudit:
    run_id: int
    ok: bool

    interval_count: int
    inverter_record_count: int
    snapshot_count: int

    total_energy_kwh: float

    issues: tuple[str, ...]


def audit_solar_run(
    db_path: str | Path,
    run_id: int,
    *,
    expected_inverter_ids: tuple[str, ...] = (
        "INV_1",
        "INV_2",
    ),
) -> SolarRunAudit:

    """
    Read-only SQLite historian audit.

    Checks:
    - SQLite integrity
    - Foreign keys
    - Timeline continuity
    - Plant energy balance
    - Inverter / plant reconciliation
    - Configuration snapshot count
    - Power provenance
    """

    if type(run_id) is not int or run_id <= 0:
        raise ValueError(
            "run_id must be positive"
        )

    if (
        not expected_inverter_ids
        or len(set(expected_inverter_ids))
        != len(expected_inverter_ids)
    ):
        raise ValueError(
            "Expected inverter IDs must be unique"
        )

    path = Path(
        db_path
    ).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(path)

    issues = []

    # SQLite read-only connection.
    uri = path.as_uri() + "?mode=ro"

    with closing(
        sqlite3.connect(uri, uri=True)
    ) as db:

        db.row_factory = sqlite3.Row

        integrity = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            issues.append(
                "SQLITE_INTEGRITY_CHECK_FAILED"
            )

        foreign_key_error = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchone()

        if foreign_key_error is not None:
            issues.append(
                "SQLITE_FOREIGN_KEY_VIOLATION"
            )

        run = db.execute(
            """
            SELECT
                interval_count,
                total_energy_kwh
            FROM simulation_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

        if run is None:
            raise ValueError(
                f"Run {run_id} not found"
            )

        plants = db.execute(
            """
            SELECT
                start_utc,
                end_utc,
                available_power_kw,
                dispatched_power_kw,
                interval_energy_kwh,
                cumulative_energy_kwh

            FROM production_intervals
            WHERE run_id = ?
            ORDER BY start_utc
            """,
            (run_id,),
        ).fetchall()

        inverter_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        snapshot_count = db.execute(
            """
            SELECT COUNT(
                DISTINCT parameter_snapshot_id
            )
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        if len(plants) != run["interval_count"]:
            issues.append(
                "PLANT_INTERVAL_COUNT_MISMATCH"
            )

        if inverter_count != (
            len(plants)
            * len(expected_inverter_ids)
        ):
            issues.append(
                "INVERTER_INTERVAL_COUNT_MISMATCH"
            )

        if snapshot_count != len(
            expected_inverter_ids
        ):
            issues.append(
                "SNAPSHOT_COUNT_MISMATCH"
            )

        running_energy = 0.0
        previous_end = None

        for plant in plants:

            start = datetime.fromisoformat(
                plant["start_utc"]
            )

            end = datetime.fromisoformat(
                plant["end_utc"]
            )

            if (
                start.utcoffset()
                != timedelta(0)
                or end - start
                != timedelta(minutes=15)
            ):
                issues.append(
                    f"BAD_INTERVAL_TIME:{plant['start_utc']}"
                )

            if (
                previous_end is not None
                and start != previous_end
            ):
                issues.append(
                    f"GAP_OR_OVERLAP:{plant['start_utc']}"
                )

            previous_end = end

            power = plant[
                "dispatched_power_kw"
            ]

            energy = plant[
                "interval_energy_kwh"
            ]

            for field in (
                "available_power_kw",
                "dispatched_power_kw",
                "interval_energy_kwh",
            ):

                value = plant[field]

                if (
                    not math.isfinite(value)
                    or value < 0
                ):
                    issues.append(
                        f"INVALID_PLANT_VALUE:"
                        f"{field}:{plant['start_utc']}"
                    )

            if not math.isclose(
                energy,
                0.25 * power,
                abs_tol=1e-6,
                rel_tol=0,
            ):
                issues.append(
                    f"PLANT_ENERGY_BALANCE:"
                    f"{plant['start_utc']}"
                )

            running_energy += energy

            if not math.isclose(
                running_energy,
                plant["cumulative_energy_kwh"],
                abs_tol=1e-6,
                rel_tol=1e-9,
            ):
                issues.append(
                    f"CUMULATIVE_ENERGY_MISMATCH:"
                    f"{plant['start_utc']}"
                )

            device_rows = db.execute(
                """
                SELECT
                    inverter_id,
                    end_utc,
                    ac_available_kw,
                    ac_dispatched_kw,
                    interval_energy_kwh,
                    quality_flags_json,
                    source_types_json,
                    power_time_semantics

                FROM ges_inverter_intervals

                WHERE run_id = ?
                  AND start_utc = ?

                ORDER BY inverter_id
                """,
                (
                    run_id,
                    plant["start_utc"],
                ),
            ).fetchall()

            ids = {
                row["inverter_id"]
                for row in device_rows
            }

            if ids != set(
                expected_inverter_ids
            ):
                issues.append(
                    f"INVERTER_SET_MISMATCH:"
                    f"{plant['start_utc']}"
                )

            if any(
                row["end_utc"]
                != plant["end_utc"]
                for row in device_rows
            ):
                issues.append(
                    f"INVERTER_END_MISMATCH:"
                    f"{plant['start_utc']}"
                )

            comparisons = (
                (
                    "ac_available_kw",
                    "available_power_kw",
                ),
                (
                    "ac_dispatched_kw",
                    "dispatched_power_kw",
                ),
                (
                    "interval_energy_kwh",
                    "interval_energy_kwh",
                ),
            )

            for inverter_field, plant_field in comparisons:

                total = math.fsum(
                    row[inverter_field]
                    for row in device_rows
                )

                if not math.isclose(
                    total,
                    plant[plant_field],
                    abs_tol=1e-6,
                    rel_tol=0,
                ):
                    issues.append(
                        f"INVERTER_"
                        f"{inverter_field.upper()}_MISMATCH:"
                        f"{plant['start_utc']}"
                    )

            for device in device_rows:

                flags = json.loads(
                    device["quality_flags_json"]
                )

                sources = json.loads(
                    device["source_types_json"]
                )

                time_semantics = device[
                    "power_time_semantics"
                ]

                if (
                    not sources
                    or not flags
                    or (
                        time_semantics
                        == "snapshot_constant_assumption"
                        and "estimated" not in flags
                    )
                ):
                    issues.append(
                        f"INVERTER_PROVENANCE_INVALID:"
                        f"{plant['start_utc']}:"
                        f"{device['inverter_id']}"
                    )

        if not math.isclose(
            running_energy,
            run["total_energy_kwh"],
            abs_tol=1e-6,
            rel_tol=1e-9,
        ):
            issues.append(
                "RUN_TOTAL_ENERGY_MISMATCH"
            )

    return SolarRunAudit(
        run_id=run_id,
        ok=not issues,
        interval_count=len(plants),
        inverter_record_count=inverter_count,
        snapshot_count=snapshot_count,
        total_energy_kwh=running_energy,
        issues=tuple(issues),
    )

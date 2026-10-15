
"""
GES Step 11.3 - Transactional inverter history writer.

This module:
- validates inverter electrical results
- checks parent plant totals
- stores inverter interval records
- records alarm transitions
- preserves parameter provenance

It never commits the caller's transaction.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone


TOL = 1e-6

POWER_COLUMNS = (
    "dc_offered_kw",
    "dc_accepted_kw",
    "dc_rejected_kw",
    "ac_unclipped_kw",
    "ac_available_kw",
    "ac_dispatched_kw",
    "conversion_loss_kw",
    "clipping_loss_kw",
    "curtailment_kw",
    "interval_energy_kwh",
)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass(frozen=True)
class InverterHistoryRow:
    run_id: int
    inverter_id: str

    start_utc: datetime
    end_utc: datetime

    dc_voltage_v: float | None

    dc_offered_kw: float
    dc_accepted_kw: float
    dc_rejected_kw: float

    ac_unclipped_kw: float
    ac_available_kw: float
    ac_dispatched_kw: float

    conversion_loss_kw: float
    clipping_loss_kw: float
    curtailment_kw: float

    interval_energy_kwh: float

    status: str

    active_alarms: tuple[str, ...]
    reasons: tuple[str, ...]

    quality_flags: tuple[str, ...]
    source_types: tuple[str, ...]

    parameter_snapshot_id: str
    power_time_semantics: str

    source_timestamp_utc: datetime | None = None
    received_at_utc: datetime | None = None


@dataclass(frozen=True)
class PlantTotals:
    run_id: int

    start_utc: datetime
    end_utc: datetime

    available_power_kw: float
    dispatched_power_kw: float
    interval_energy_kwh: float


# ============================================================
# VALIDATION HELPERS
# ============================================================

def utc_db(value: datetime) -> str:
    """
    Match existing APP timestamp format:

    2026-06-21T10:00:00+00:00

    Do not replace +00:00 with Z.
    """

    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
    ):
        raise ValueError(
            "Timezone-aware UTC timestamp required"
        )

    if value.utcoffset() != timedelta(0):
        raise ValueError(
            "Timestamp must have UTC offset"
        )

    precision = (
        "microseconds"
        if value.microsecond
        else "seconds"
    )

    return value.astimezone(
        timezone.utc
    ).isoformat(timespec=precision)


def check_number(
    label: str,
    value: float,
) -> None:

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"{label} must be nonnegative and finite"
        )


def approx(
    label: str,
    left: float,
    right: float,
    tol: float = TOL,
) -> None:

    if not math.isclose(
        left,
        right,
        rel_tol=0,
        abs_tol=tol,
    ):
        raise ValueError(
            f"{label}: {left} != {right}"
        )


def check_time(
    start: datetime,
    end: datetime,
) -> None:

    utc_db(start)
    utc_db(end)

    if end - start != timedelta(minutes=15):
        raise ValueError(
            "Interval must be exactly 15 minutes"
        )

    if (
        start.minute % 15
        or start.second
        or start.microsecond
    ):
        raise ValueError(
            "Interval must start on UTC quarter-hour"
        )


# ============================================================
# INVERTER RECORD VALIDATION
# ============================================================

def check_row(
    row: InverterHistoryRow,
) -> None:

    if (
        type(row.run_id) is not int
        or row.run_id <= 0
    ):
        raise ValueError("Invalid run ID")

    if (
        not isinstance(row.inverter_id, str)
        or not row.inverter_id.strip()
    ):
        raise ValueError("Missing inverter ID")

    if (
        not isinstance(
            row.parameter_snapshot_id,
            str,
        )
        or not row.parameter_snapshot_id.strip()
    ):
        raise ValueError(
            "Missing parameter snapshot ID"
        )

    check_time(
        row.start_utc,
        row.end_utc,
    )

    # Reject unknown, negative and non-finite power.

    for field in POWER_COLUMNS:
        check_number(
            field,
            getattr(row, field),
        )

    if row.dc_voltage_v is not None:
        check_number(
            "dc_voltage_v",
            row.dc_voltage_v,
        )

    # Explicit inverter statuses.

    if row.status not in {
        "RUNNING",
        "CURTAILED",
        "IDLE",
        "BLOCKED",
    }:
        raise ValueError(
            "Unknown inverter status"
        )

    # Quality and source metadata.

    for field in (
        "active_alarms",
        "reasons",
        "quality_flags",
        "source_types",
    ):

        items = getattr(row, field)

        if (
            not isinstance(items, tuple)
            or any(
                not isinstance(item, str)
                or not item.strip()
                for item in items
            )
            or len(items) != len(set(items))
        ):
            raise ValueError(
                f"Invalid {field}"
            )

    if (
        not row.quality_flags
        or not row.source_types
    ):
        raise ValueError(
            "Missing quality/source tags"
        )

    if row.power_time_semantics not in {
        "interval_mean",
        "snapshot_constant_assumption",
    }:
        raise ValueError(
            "Unknown power time semantics"
        )

    if (
        row.power_time_semantics
        == "snapshot_constant_assumption"
        and "estimated" not in row.quality_flags
    ):
        raise ValueError(
            "Snapshot-based power must be "
            "flagged estimated"
        )

    for time_value in (
        row.source_timestamp_utc,
        row.received_at_utc,
    ):
        if time_value is not None:
            utc_db(time_value)

    # Electrical constraints.

    if (
        row.dc_accepted_kw
        > row.dc_offered_kw + TOL
    ):
        raise ValueError(
            "Accepted DC exceeds offered DC"
        )

    if (
        row.ac_dispatched_kw
        > row.ac_available_kw + TOL
    ):
        raise ValueError(
            "Dispatched AC exceeds available AC"
        )

    approx(
        "curtailment",
        row.ac_available_kw - row.ac_dispatched_kw,
        row.curtailment_kw,
    )

    approx(
        "interval energy",
        row.ac_dispatched_kw * 0.25,
        row.interval_energy_kwh,
        TOL * 0.25,
    )

    if row.status == "BLOCKED":

        approx(
            "blocked dispatched power",
            row.ac_dispatched_kw,
            0.0,
        )

        if (
            not row.active_alarms
            and not row.reasons
        ):
            raise ValueError(
                "BLOCKED requires a reason or alarm"
            )

    else:

        approx(
            "DC balance",
            row.dc_offered_kw - row.dc_accepted_kw,
            row.dc_rejected_kw,
        )

        approx(
            "conversion balance",
            row.dc_accepted_kw - row.ac_unclipped_kw,
            row.conversion_loss_kw,
        )

        approx(
            "clipping balance",
            row.ac_unclipped_kw - row.ac_available_kw,
            row.clipping_loss_kw,
        )


# ============================================================
# DATABASE TRANSACTION REQUIREMENTS
# ============================================================

def require_transaction(
    db: sqlite3.Connection,
) -> None:

    if not db.in_transaction:
        raise ValueError(
            "Caller must start a transaction"
        )

    if db.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0] != 1:
        raise ValueError(
            "Enable SQLite foreign keys "
            "before transaction"
        )


# ============================================================
# CONTENT-ADDRESSED PARAMETER SNAPSHOTS
# ============================================================

def register_parameter_snapshot(
    db: sqlite3.Connection,
    payload: dict,
) -> str:

    """
    Store a parameter snapshot with SHA256 identity.

    Effective values and source provenance must
    be supplied by the caller.
    """

    require_transaction(db)

    if not isinstance(payload, dict):
        raise ValueError(
            "Snapshot payload must be a dict"
        )

    for key in (
        "component_id",
        "model_id",
    ):
        value = payload.get(key)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                f"Snapshot requires {key}"
            )

    values = payload.get("values")

    if (
        not isinstance(values, dict)
        or not values
    ):
        raise ValueError(
            "Snapshot requires parameter values"
        )

    for name, item in values.items():

        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(item, dict)
            or "value" not in item
            or any(
                not item.get(key)
                for key in (
                    "source_id",
                    "source_url",
                    "evidence",
                )
            )
        ):
            raise ValueError(
                "Incomplete parameter provenance"
            )

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    snapshot_id = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    db.execute(
        """
        INSERT INTO ges_parameter_snapshots
        (
            snapshot_id,
            component_id,
            model_id,
            payload_json
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(snapshot_id) DO NOTHING
        """,
        (
            snapshot_id,
            payload["component_id"],
            payload["model_id"],
            canonical,
        ),
    )

    return snapshot_id


# ============================================================
# ATOMIC INVERTER INTERVAL WRITER
# ============================================================

def save_inverter_interval(
    db: sqlite3.Connection,
    rows: list[InverterHistoryRow],
    plant: PlantTotals,
    *,
    expected_inverter_ids: tuple[str, ...],
) -> None:

    """
    Append inverter data to an existing plant interval.

    The caller owns BEGIN, COMMIT and ROLLBACK.

    This function:
    - validates records
    - checks plant totals
    - verifies the stored parent row
    - writes both inverters atomically
    - records alarm transitions
    - checks persisted totals

    No automatic commit occurs.
    """

    require_transaction(db)

    check_time(
        plant.start_utc,
        plant.end_utc,
    )

    if (
        type(plant.run_id) is not int
        or plant.run_id <= 0
    ):
        raise ValueError(
            "Invalid plant run ID"
        )

    # Validate expected inverter identifiers.

    if (
        not expected_inverter_ids
        or len(set(expected_inverter_ids))
        != len(expected_inverter_ids)
        or any(
            not isinstance(item, str)
            or not item.strip()
            for item in expected_inverter_ids
        )
    ):
        raise ValueError(
            "Expected inverter IDs invalid"
        )

    actual_ids = [
        row.inverter_id
        for row in rows
    ]

    if (
        len(actual_ids) != len(set(actual_ids))
        or set(actual_ids)
        != set(expected_inverter_ids)
    ):
        raise ValueError(
            "Missing, extra, or duplicate inverter"
        )

    # Validate each inverter and its interval.

    for row in rows:

        check_row(row)

        if (
            row.run_id,
            row.start_utc,
            row.end_utc,
        ) != (
            plant.run_id,
            plant.start_utc,
            plant.end_utc,
        ):
            raise ValueError(
                "Plant/inverter run or "
                "timestamps mismatch"
            )

    # Validate plant power totals.

    for field in (
        "available_power_kw",
        "dispatched_power_kw",
        "interval_energy_kwh",
    ):
        check_number(
            field,
            getattr(plant, field),
        )

    approx(
        "plant available",
        math.fsum(
            row.ac_available_kw
            for row in rows
        ),
        plant.available_power_kw,
    )

    approx(
        "plant dispatched",
        math.fsum(
            row.ac_dispatched_kw
            for row in rows
        ),
        plant.dispatched_power_kw,
    )

    approx(
        "plant energy",
        math.fsum(
            row.interval_energy_kwh
            for row in rows
        ),
        plant.interval_energy_kwh,
        TOL * 0.25,
    )

    # Verify actual stored production interval.

    parent = db.execute(
        """
        SELECT
            available_power_kw,
            dispatched_power_kw,
            interval_energy_kwh
        FROM production_intervals
        WHERE run_id = ?
          AND start_utc = ?
        """,
        (
            plant.run_id,
            utc_db(plant.start_utc),
        ),
    ).fetchone()

    if parent is None:
        raise ValueError(
            "Plant parent interval "
            "must be saved first"
        )

    labels = (
        "available",
        "dispatched",
        "energy",
    )

    expected_values = (
        plant.available_power_kw,
        plant.dispatched_power_kw,
        plant.interval_energy_kwh,
    )

    tolerances = (
        TOL,
        TOL,
        TOL * 0.25,
    )

    for label, stored, expected, tol in zip(
        labels,
        parent,
        expected_values,
        tolerances,
    ):

        check_number(
            "Parent " + label,
            stored,
        )

        approx(
            "Parent " + label,
            stored,
            expected,
            tol,
        )

    # The inverter set must remain fixed
    # throughout a simulation run.

    old_ids = {
        record[0]
        for record in db.execute(
            """
            SELECT DISTINCT inverter_id
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (plant.run_id,),
        )
    }

    if (
        old_ids
        and old_ids != set(expected_inverter_ids)
    ):
        raise ValueError(
            "Inverter set changed within run"
        )

    # Prevent duplicate, backward or gapped writes.

    for row in rows:

        prior = db.execute(
            """
            SELECT end_utc
            FROM ges_inverter_intervals
            WHERE run_id = ?
              AND inverter_id = ?
            ORDER BY start_utc DESC
            LIMIT 1
            """,
            (
                row.run_id,
                row.inverter_id,
            ),
        ).fetchone()

        if (
            prior
            and prior[0] != utc_db(row.start_utc)
        ):
            raise ValueError(
                "Overlapping/duplicate/gapped interval"
            )

    # Savepoint: either the whole interval
    # is stored or none of its inverter rows.

    db.execute(
        "SAVEPOINT ges_inverter_insert"
    )

    try:

        for row in rows:

            prior = db.execute(
                """
                SELECT active_alarms_json
                FROM ges_inverter_intervals
                WHERE run_id = ?
                  AND inverter_id = ?
                ORDER BY start_utc DESC
                LIMIT 1
                """,
                (
                    row.run_id,
                    row.inverter_id,
                ),
            ).fetchone()

            previous_alarms = (
                set(json.loads(prior[0]))
                if prior
                else set()
            )

            payload = asdict(row)

            for name in (
                "start_utc",
                "end_utc",
                "source_timestamp_utc",
                "received_at_utc",
            ):

                value = payload[name]

                payload[name] = (
                    utc_db(value)
                    if value is not None
                    else None
                )

            for name in (
                "active_alarms",
                "reasons",
                "quality_flags",
                "source_types",
            ):

                payload[name + "_json"] = json.dumps(
                    payload.pop(name),
                    ensure_ascii=False,
                    allow_nan=False,
                )

            columns = tuple(payload)

            db.execute(
                "INSERT INTO ges_inverter_intervals ("
                + ", ".join(columns)
                + ") VALUES ("
                + ", ".join(
                    "?"
                    for _ in columns
                )
                + ")",
                tuple(
                    payload[name]
                    for name in columns
                ),
            )

            # Alarm transitions are detected at
            # the interval boundary, not at
            # the actual physical fault instant.

            alarms = set(row.active_alarms)

            transitions = (
                (
                    alarms - previous_alarms,
                    "RAISED",
                ),
                (
                    previous_alarms - alarms,
                    "CLEARED",
                ),
            )

            for codes, transition in transitions:

                for code in sorted(codes):

                    db.execute(
                        """
                        INSERT INTO
                        ges_inverter_alarm_events
                        (
                            run_id,
                            inverter_id,
                            interval_start_utc,
                            timestamp_utc,
                            code,
                            transition,
                            time_semantics
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row.run_id,
                            row.inverter_id,
                            utc_db(row.start_utc),
                            utc_db(row.start_utc),
                            code,
                            transition,
                            "interval_boundary_detection",
                        ),
                    )

        # Verify stored inverter sums again.

        saved = db.execute(
            """
            SELECT
                COUNT(*),
                SUM(ac_available_kw),
                SUM(ac_dispatched_kw),
                SUM(interval_energy_kwh)
            FROM ges_inverter_intervals
            WHERE run_id = ?
              AND start_utc = ?
            """,
            (
                plant.run_id,
                utc_db(plant.start_utc),
            ),
        ).fetchone()

        if saved[0] != len(expected_inverter_ids):
            raise ValueError(
                "Persisted inverter count mismatch"
            )

        stored_labels = (
            "DB available",
            "DB dispatched",
            "DB energy",
        )

        for label, actual, expected, tol in zip(
            stored_labels,
            saved[1:],
            expected_values,
            tolerances,
        ):

            approx(
                label,
                actual,
                expected,
                tol,
            )

        db.execute(
            "RELEASE SAVEPOINT ges_inverter_insert"
        )

    except BaseException:

        db.execute(
            "ROLLBACK TO SAVEPOINT ges_inverter_insert"
        )

        db.execute(
            "RELEASE SAVEPOINT ges_inverter_insert"
        )

        raise

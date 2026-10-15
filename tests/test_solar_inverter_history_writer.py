
import sqlite3

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from simulator.solar.inverter_history_writer import (
    InverterHistoryRow,
    PlantTotals,
    register_parameter_snapshot,
    save_inverter_interval,
)


SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "simulator/solar/ges_history_schema.sql"
)

START = datetime(
    2026, 6, 21, 10, 0,
    tzinfo=timezone.utc,
)


def db_with_parent(
    start=START,
    *,
    available=10,
    dispatched=8.5,
    energy=2.125,
):

    db = sqlite3.connect(":memory:")

    db.execute(
        "PRAGMA foreign_keys=ON"
    )

    db.execute(
        "CREATE TABLE production_intervals ("
        "run_id INTEGER NOT NULL, "
        "start_utc TEXT NOT NULL, "
        "available_power_kw REAL NOT NULL, "
        "dispatched_power_kw REAL NOT NULL, "
        "interval_energy_kwh REAL NOT NULL, "
        "PRIMARY KEY(run_id,start_utc))"
    )

    db.executescript(
        SCHEMA.read_text(encoding="utf-8")
    )

    db.execute(
        "INSERT INTO production_intervals "
        "VALUES (?,?,?,?,?)",
        (
            1,
            start.isoformat(),
            available,
            dispatched,
            energy,
        ),
    )

    db.commit()

    return db


def snapshot(db):

    return register_parameter_snapshot(
        db,
        {
            "component_id": "TEST_INVERTER",
            "model_id": "synthetic",
            "values": {
                "rated_ac": {
                    "value": 100,
                    "source_id": "TEST",
                    "source_url":
                        "https://example.com/test-datasheet",
                    "evidence": "synthetic fixture",
                }
            },
        },
    )


def rows(start, snapshot_id):

    base = dict(
        run_id=1,
        start_utc=start,
        end_utc=start + timedelta(minutes=15),
        dc_voltage_v=None,
        status="RUNNING",
        active_alarms=(),
        reasons=(),
        quality_flags=("estimated",),
        source_types=("synthetic",),
        parameter_snapshot_id=snapshot_id,
        power_time_semantics=(
            "snapshot_constant_assumption"
        ),
    )

    return [
        InverterHistoryRow(
            inverter_id="INV_1",
            dc_offered_kw=6,
            dc_accepted_kw=6,
            dc_rejected_kw=0,
            ac_unclipped_kw=5.7,
            ac_available_kw=5.5,
            ac_dispatched_kw=4.5,
            conversion_loss_kw=0.3,
            clipping_loss_kw=0.2,
            curtailment_kw=1,
            interval_energy_kwh=1.125,
            **base,
        ),
        InverterHistoryRow(
            inverter_id="INV_2",
            dc_offered_kw=5,
            dc_accepted_kw=5,
            dc_rejected_kw=0,
            ac_unclipped_kw=4.8,
            ac_available_kw=4.5,
            ac_dispatched_kw=4,
            conversion_loss_kw=0.2,
            clipping_loss_kw=0.3,
            curtailment_kw=0.5,
            interval_energy_kwh=1,
            **base,
        ),
    ]


def totals(
    start=START,
    *,
    available=10,
    dispatched=8.5,
    energy=2.125,
):

    return PlantTotals(
        1,
        start,
        start + timedelta(minutes=15),
        available,
        dispatched,
        energy,
    )


def write(db, records, plant=None):

    return save_inverter_interval(
        db,
        records,
        plant or totals(),
        expected_inverter_ids=(
            "INV_1",
            "INV_2",
        ),
    )


def test_two_inverters_and_parent_timestamp():

    with db_with_parent() as db:

        db.execute("BEGIN")
        sid = snapshot(db)

        write(db, rows(START, sid))

        assert db.in_transaction

        assert db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0] == 2

        assert db.execute(
            "SELECT start_utc "
            "FROM ges_inverter_intervals LIMIT 1"
        ).fetchone()[0] == (
            "2026-06-21T10:00:00+00:00"
        )


def test_snapshot_content_hash():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid1 = snapshot(db)
        sid2 = snapshot(db)

        assert sid1 == sid2

        assert db.execute(
            "SELECT COUNT(*) "
            "FROM ges_parameter_snapshots"
        ).fetchone()[0] == 1


def test_transaction_is_required():

    with db_with_parent() as db:

        with pytest.raises(
            ValueError,
            match="transaction",
        ):
            snapshot(db)


def test_missing_inverter_is_rejected():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        with pytest.raises(
            ValueError,
            match="Missing",
        ):
            write(
                db,
                rows(START, sid)[:1],
            )

        assert db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0] == 0


def test_parent_total_mismatch_is_rejected():

    with db_with_parent(available=12) as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        with pytest.raises(
            ValueError,
            match="Parent",
        ):
            write(
                db,
                rows(START, sid),
            )


def test_second_insert_failure_rolls_back_first():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        records = rows(START, sid)

        records[1] = replace(
            records[1],
            parameter_snapshot_id="unknown",
        )

        with pytest.raises(
            sqlite3.IntegrityError
        ):
            write(db, records)

        assert db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0] == 0

        assert db.in_transaction


def test_unbalanced_losses_are_rejected():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        records = rows(START, sid)

        records[0] = replace(
            records[0],
            clipping_loss_kw=1.0,
        )

        with pytest.raises(
            ValueError,
            match="clipping balance",
        ):
            write(db, records)


def test_duplicate_interval_is_rejected():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        records = rows(START, sid)

        write(db, records)

        with pytest.raises(
            ValueError,
            match="Overlapping",
        ):
            write(db, records)

        assert db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0] == 2


def test_snapshot_power_requires_estimated_tag():

    with db_with_parent() as db:

        db.execute("BEGIN")

        sid = snapshot(db)

        records = rows(START, sid)

        records[0] = replace(
            records[0],
            quality_flags=("synthetic",),
        )

        with pytest.raises(
            ValueError,
            match="estimated",
        ):
            write(db, records)

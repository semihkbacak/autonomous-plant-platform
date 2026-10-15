
import sqlite3

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from simulator.solar.inverter import InverterResult

from simulator.solar.inverter_history_adapter import (
    build_inverter_history_rows,
    append_simulated_inverter_interval,
)

from simulator.solar.inverter_history_writer import (
    register_parameter_snapshot,
)


START = datetime(
    2026, 6, 21, 10, 0,
    tzinfo=timezone.utc,
)

SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "simulator/solar/ges_history_schema.sql"
)


def sample_inverters():

    return (
        InverterResult(
            inverter_id="INV_1",
            status="RUNNING",
            dc_offered_kw=6,
            dc_accepted_kw=6,
            ac_unclipped_kw=5.7,
            ac_available_kw=5.5,
            ac_dispatched_kw=4.5,
            dc_rejected_kw=0,
            conversion_loss_kw=0.3,
            clipping_loss_kw=0.2,
            curtailment_kw=1,
            reasons=(),
        ),
        InverterResult(
            inverter_id="INV_2",
            status="RUNNING",
            dc_offered_kw=5,
            dc_accepted_kw=5,
            ac_unclipped_kw=4.8,
            ac_available_kw=4.5,
            ac_dispatched_kw=4,
            dc_rejected_kw=0,
            conversion_loss_kw=0.2,
            clipping_loss_kw=0.3,
            curtailment_kw=0.5,
            reasons=(),
        ),
    )


def sample_record(
    inverters=None,
    alarms=(),
):

    return SimpleNamespace(
        start_utc=START,
        end_utc=START + timedelta(minutes=15),
        inverter_results=(
            sample_inverters()
            if inverters is None
            else inverters
        ),
        available_power_kw=10,
        dispatched_power_kw=8.5,
        interval_energy_kwh=2.125,
        quality_flags=("synthetic",),
        source_types=("simulation",),
        active_alarms=alarms,
    )


def convert(record, snapshots=None):

    return build_inverter_history_rows(
        record,
        run_id=1,
        expected_inverter_ids=("INV_1", "INV_2"),
        parameter_snapshot_ids=(
            {"INV_1": "snap1", "INV_2": "snap2"}
            if snapshots is None
            else snapshots
        ),
    )


def test_real_inverter_result_fields_are_mapped():

    rows = convert(sample_record())

    assert len(rows) == 2

    assert rows[0].dc_offered_kw == 6
    assert rows[0].ac_available_kw == 5.5
    assert rows[0].ac_dispatched_kw == 4.5
    assert rows[0].interval_energy_kwh == 1.125

    assert rows[1].interval_energy_kwh == 1.0

    assert rows[0].dc_voltage_v is None
    assert "estimated" in rows[0].quality_flags

    assert rows[0].power_time_semantics == (
        "snapshot_constant_assumption"
    )


def test_plant_alarm_not_copied_to_each_inverter():

    record = sample_record(
        alarms=(
            "GRID_UNAVAILABLE",
            "INVERTER_FAULT:INV_2",
        )
    )

    rows = convert(record)

    assert rows[0].active_alarms == ()
    assert rows[1].active_alarms == (
        "INVERTER_FAULT",
    )


def test_missing_inverter_is_rejected():

    record = sample_record(
        inverters=sample_inverters()[:1]
    )

    with pytest.raises(
        ValueError,
        match="Missing",
    ):
        convert(record)


def test_missing_snapshot_is_rejected():

    with pytest.raises(
        ValueError,
        match="snapshot",
    ):
        convert(
            sample_record(),
            snapshots={"INV_1": "snap1"},
        )


def test_unknown_alarm_target_is_rejected():

    record = sample_record(
        alarms=("INVERTER_FAULT:INV_99",)
    )

    with pytest.raises(
        ValueError,
        match="Unknown inverter",
    ):
        convert(record)


def test_adapter_writes_both_inverters_to_sqlite():

    db = sqlite3.connect(":memory:")

    try:
        db.execute("PRAGMA foreign_keys=ON")

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
            "VALUES (?, ?, ?, ?, ?)",
            (
                1,
                START.isoformat(),
                10,
                8.5,
                2.125,
            ),
        )

        db.commit()
        db.execute("BEGIN")

        snapshot_ids = {}

        for inverter_id in ("INV_1", "INV_2"):

            snapshot_ids[inverter_id] = (
                register_parameter_snapshot(
                    db,
                    {
                        "component_id": inverter_id,
                        "model_id": "TEST_ONLY",
                        "values": {
                            "test_parameter": {
                                "value": 1,
                                "source_id": "TEST",
                                "source_url": (
                                    "fixture://synthetic"
                                ),
                                "evidence": (
                                    "synthetic test"
                                ),
                            }
                        },
                    },
                )
            )

        append_simulated_inverter_interval(
            db,
            run_id=1,
            record=sample_record(),
            expected_inverter_ids=(
                "INV_1",
                "INV_2",
            ),
            parameter_snapshot_ids=snapshot_ids,
        )

        count = db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0]

        dispatched = db.execute(
            "SELECT SUM(ac_dispatched_kw) "
            "FROM ges_inverter_intervals"
        ).fetchone()[0]

        assert count == 2
        assert dispatched == pytest.approx(8.5)
        assert db.in_transaction

    finally:
        db.close()

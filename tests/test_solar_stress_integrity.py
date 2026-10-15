
import sqlite3

import pytest

from demo_ges_timeseries import (
    build_demo_pipeline,
)

from simulator.solar.historian import (
    SolarHistorian,
)

from simulator.solar.inverter_snapshot_payloads import (
    build_demo_inverter_snapshot_payloads,
)

from simulator.solar.solar_historian_audit import (
    audit_solar_run,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)


@pytest.fixture(scope="module")
def prepared():

    pipeline = build_demo_pipeline()

    inputs = make_stress_intervals(
        1,
        latitude_deg=pipeline.site.latitude_deg,
        longitude_deg=pipeline.site.longitude_deg,
    )

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    for item in inputs:
        simulator.step(item)

    return simulator, pipeline, inputs


def store(tmp_path, prepared):

    simulator, pipeline, _ = prepared

    path = tmp_path / "stress.sqlite3"

    run_id = SolarHistorian(
        path
    ).save_simulation(
        simulator,

        scenario="SYNTHETIC_STRESS_1D",

        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    return path, run_id


def test_profile_is_contiguous_and_day_night():

    inputs = make_stress_intervals(1)

    assert len(inputs) == 96

    assert all(
        first.end_utc == second.start_utc
        for first, second in zip(
            inputs,
            inputs[1:],
        )
    )

    assert (
        inputs[0].weather.irradiance.ghi_w_m2
        == 0
    )

    assert (
        inputs[48].weather.irradiance.ghi_w_m2
        > 0
    )


def test_fault_and_grid_disturbance_plan():

    items = make_stress_intervals(1)

    assert not items[40].grid_available
    assert not items[41].grid_available

    assert items[42].grid_available

    assert items[48].fault_inverter_ids == (
        frozenset({"INV_2"})
    )

    assert items[56].emergency_stop

    assert items[64].maintenance_inverter_ids == (
        frozenset({"INV_1"})
    )

    assert items[44].requested_target_kw == 5.0


def test_invalid_day_counts():

    for value in (
        0,
        -1,
        366,
        True,
        1.5,
    ):
        assert len(make_stress_intervals(180)) == 17280
        with pytest.raises(ValueError):
            make_stress_intervals(
                value
            )


def test_one_day_energy_and_zero_dispatch(
    prepared,
):

    simulator, _, _ = prepared

    assert len(simulator.records) == 96

    assert (
        simulator.records[0].dispatched_power_kw
        == 0
    )

    assert all(
        simulator.records[index].dispatched_power_kw
        == 0

        for index in (
            40,
            41,
            56,
        )
    )

    for record in simulator.records:

        assert record.interval_energy_kwh == (
            pytest.approx(
                record.dispatched_power_kw / 4
            )
        )

    assert (
        simulator.records[-1].cumulative_energy_kwh
        == pytest.approx(
            sum(
                record.interval_energy_kwh
                for record in simulator.records
            )
        )
    )

    grid_events = [
        event
        for event in simulator.alarm_history
        if event.code == "GRID_UNAVAILABLE"
    ]

    assert len(grid_events) == 2


def test_utc_gap_is_rejected(
    prepared,
):

    _, pipeline, items = prepared

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    simulator.step(items[0])

    with pytest.raises(
        ValueError,
        match="consecutive",
    ):
        simulator.step(
            items[2]
        )


def test_inverter_historian_audit_passes(
    prepared,
    tmp_path,
):

    path, run_id = store(
        tmp_path,
        prepared,
    )

    result = audit_solar_run(
        path,
        run_id,
    )

    assert result.ok, result.issues

    assert result.interval_count == 96

    assert result.inverter_record_count == 192

    assert result.snapshot_count == 2

    assert result.total_energy_kwh > 0


def test_audit_detects_missing_inverter(
    prepared,
    tmp_path,
):

    path, run_id = store(
        tmp_path,
        prepared,
    )

    with sqlite3.connect(path) as db:

        db.execute(
            """
            DELETE FROM ges_inverter_intervals
            WHERE run_id = ?
              AND inverter_id = ?
              AND start_utc = ?
            """,
            (
                run_id,
                "INV_1",
                prepared[0].records[3].start_utc.isoformat(),
            ),
        )

    result = audit_solar_run(
        path,
        run_id,
    )

    assert not result.ok

    assert any(
        "INVERTER" in issue
        for issue in result.issues
    )


def test_audit_detects_inverter_power_drift(
    prepared,
    tmp_path,
):

    path, run_id = store(
        tmp_path,
        prepared,
    )

    with sqlite3.connect(path) as db:

        db.execute(
            """
            UPDATE ges_inverter_intervals
            SET ac_dispatched_kw =
                ac_dispatched_kw + 1

            WHERE run_id = ?
              AND inverter_id = ?
              AND start_utc = ?
            """,
            (
                run_id,
                "INV_1",
                prepared[0].records[50].start_utc.isoformat(),
            ),
        )

    result = audit_solar_run(
        path,
        run_id,
    )

    assert not result.ok

    assert any(
        "DISPATCHED" in issue
        for issue in result.issues
    )


def test_missing_database_is_not_created(
    tmp_path,
):

    missing = (
        tmp_path
        / "unknown.sqlite3"
    )

    with pytest.raises(
        FileNotFoundError
    ):
        audit_solar_run(
            missing,
            1,
        )

    assert not missing.exists()

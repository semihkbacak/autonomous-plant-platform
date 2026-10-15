
"""GES v0.4 integrated regression tests."""
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.solar_mppt_api import (
    create_solar_mppt_router,
)

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
    InverterMPPTConfig,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.pq_dispatch import (
    PQCapability,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


ROOT = Path(__file__).resolve().parents[1]

WEATHER = (
    ROOT / "data/solar/demo_weather_15m.csv"
)


def get_weather():
    return load_weather_intervals_csv(WEATHER)


def pq(pipeline, q=8.0):
    return (
        {
            iid: PQCapability(10, 10)
            for iid in pipeline.inverter_ids
        },
        {
            iid: q
            for iid in pipeline.inverter_ids
        },
    )


def test_two_inverters_four_distinct_mppt_channels():

    pipeline = build_integrated_demo_pipeline()

    result = pipeline.simulate(
        get_weather()[1].weather
    )

    assert len(result.mppt_reports) == 2
    assert len(result.array_reports) == 4

    assert {
        report.inverter_id
        for report in result.mppt_reports
    } == {"INV_1", "INV_2"}

    assert sum(
        len(report.dc.channels)
        for report in result.mppt_reports
    ) == 4

    assert result.plant.dispatched_power_kw == pytest.approx(
        sum(
            inverter.ac_dispatched_kw
            for inverter in result.plant.inverter_results
        )
    )

    for report, inverter in zip(
        result.mppt_reports,
        result.plant.inverter_results,
    ):
        assert (
            report.dc.dc_accepted_kw
            == pytest.approx(inverter.dc_accepted_kw)
        )

        assert (
            report.dc.dc_offered_kw
            == pytest.approx(inverter.dc_offered_kw)
        )

        assert report.dc.dc_offered_kw == pytest.approx(
            report.dc.dc_accepted_kw
            + report.dc.dc_rejected_kw
        )


def test_nonidentical_mppt_voltages_are_not_added():

    original = build_integrated_demo_pipeline()

    configs = dict(
        original.mppt_configs
    )

    iid = "INV_1"

    old = configs[iid]

    altered = replace(
        old.channels[1],
        array=replace(
            old.channels[1].array,
            modules_per_string=9,
        ),
    )

    configs[iid] = InverterMPPTConfig(
        (old.channels[0], altered),
        old.limits,
    )

    pipeline = IntegratedSolarPhysicsPipeline(
        original.site,
        original.assets,
        configs,
    )

    result = pipeline.simulate(
        get_weather()[1].weather
    )

    channels = result.mppt_reports[0].dc.channels

    assert len(channels) == 2

    assert channels[0].voltage_v != pytest.approx(
        channels[1].voltage_v
    )

    assert (
        result.mppt_reports[0].dc.dc_accepted_kw
        == pytest.approx(
            channels[0].accepted_kw
            + channels[1].accepted_kw
        )
    )


def test_pq_reduces_single_converted_ac_once():

    pipeline = build_integrated_demo_pipeline()

    weather = get_weather()[1].weather

    unconstrained = pipeline.simulate(weather)

    capabilities, q_requests = pq(
        pipeline,
        8.0,
    )

    constrained = pipeline.simulate(
        weather,
        pq_capabilities=capabilities,
        reactive_requests_kvar=q_requests,
    )

    assert (
        constrained.plant.dispatched_power_kw
        <= 12.0 + 1e-8
    )

    assert (
        constrained.plant.dispatched_power_kw
        <= unconstrained.plant.dispatched_power_kw
    )

    assert (
        constrained.plant.curtailed_power_kw
        == pytest.approx(
            constrained.plant.available_power_kw
            - constrained.plant.dispatched_power_kw
        )
    )


def test_grid_loss_blocks_ac_but_retains_mppt_offers():

    pipeline = build_integrated_demo_pipeline()

    result = pipeline.simulate(
        get_weather()[1].weather,
        grid_available=False,
    )

    assert result.plant.dispatched_power_kw == 0

    assert all(
        inverter.status == "BLOCKED"
        for inverter in result.plant.inverter_results
    )

    assert sum(
        report.dc.dc_offered_kw
        for report in result.mppt_reports
    ) > 0


def test_mismatched_reactive_configuration_rejected():

    pipeline = build_integrated_demo_pipeline()

    with pytest.raises(
        ValueError,
        match="Both P-Q",
    ):
        pipeline.simulate(
            get_weather()[1].weather,
            pq_capabilities={},
        )

    capabilities, q_requests = pq(
        pipeline,
        11.0,
    )

    with pytest.raises(
        ValueError,
        match="Reactive request infeasible",
    ):
        pipeline.simulate(
            get_weather()[1].weather,
            pq_capabilities=capabilities,
            reactive_requests_kvar=q_requests,
        )


def save_four_intervals(tmp_path):

    pipeline = build_integrated_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    capabilities, q_requests = pq(pipeline)

    for index, weather in enumerate(
        get_weather()[:4]
    ):

        simulator.step(
            SolarIntervalInput(
                start_utc=weather.start_utc,
                end_utc=weather.end_utc,
                weather=weather.weather,
                grid_available=(index != 2),
                pq_capabilities=capabilities,
                reactive_requests_kvar=q_requests,
            )
        )

    file = tmp_path / "v04.sqlite3"

    historian = SolarHistorian(file)

    run_id = historian.save_simulation(
        simulator,
        inverter_snapshot_payloads=(
            build_integrated_snapshots(pipeline)
        ),
    )

    return simulator, historian, run_id, file


def test_mppt_historian_persists_and_reopens(tmp_path):

    simulator, historian, run_id, file = (
        save_four_intervals(tmp_path)
    )

    with sqlite3.connect(file) as db:

        assert db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

        rows = db.execute(
            """
            SELECT inverter_id, channel, dc_accepted_kw
            FROM ges_mppt_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

        assert len(rows) == 16

        assert {
            row[1]
            for row in rows
        } == {1, 2}

        assert db.execute(
            """
            SELECT COUNT(*)
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0] == 8

        assert db.execute(
            """
            SELECT COUNT(*)
            FROM ges_pq_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0] == 8

    reopened = SolarHistorian(file)

    assert reopened.list_runs()[0]["id"] == run_id


def test_bad_mppt_history_rolls_back_plant_and_inverters(
    tmp_path,
):

    pipeline = build_integrated_demo_pipeline()

    weather = get_weather()[0]

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    simulator.step(
        SolarIntervalInput(
            start_utc=weather.start_utc,
            end_utc=weather.end_utc,
            weather=weather.weather,
        )
    )

    record = simulator.records[0]

    first = replace(
        record.mppt_reports[0],
        inverter_id="UNKNOWN_INVERTER",
    )

    simulator.records[0] = replace(
        record,
        mppt_reports=(
            first,
            *record.mppt_reports[1:],
        ),
    )

    historian = SolarHistorian(
        tmp_path / "atomic.sqlite3"
    )

    with pytest.raises(
        ValueError,
        match="Unknown or duplicate MPPT inverter",
    ):
        historian.save_simulation(
            simulator,
            inverter_snapshot_payloads=(
                build_integrated_snapshots(pipeline)
            ),
        )

    assert historian.list_runs() == []


def test_mppt_api_reads_saved_channels(tmp_path):

    _, _, run_id, file = save_four_intervals(
        tmp_path
    )

    app = FastAPI()

    app.include_router(
        create_solar_mppt_router(file)
    )

    client = TestClient(app)

    response = client.get(
        f"/solar/mppt/runs/{run_id}/intervals?limit=100"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 16
    assert "reasons" in data[0]

    assert client.get(
        "/solar/mppt/dashboard"
    ).status_code == 200

    assert client.get(
        "/solar/mppt/runs"
    ).json()[0]["mppt_record_count"] == 16

    q_values = client.get(
        f"/solar/mppt/runs/{run_id}/pq"
    ).json()

    assert len(q_values) == 8

    assert all(
        row["reactive_value_kind"]
        == "REQUEST_NOT_MEASURED"
        for row in q_values
    )

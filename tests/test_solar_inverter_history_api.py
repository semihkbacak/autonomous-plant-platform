
from pathlib import Path

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.solar_inverter_history_api import (
    create_solar_inverter_history_router,
)

from demo_ges_timeseries import (
    build_demo_pipeline,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.inverter_snapshot_payloads import (
    build_demo_inverter_snapshot_payloads,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


WEATHER = (
    Path(__file__).resolve().parents[1]
    / "data/solar/demo_weather_15m.csv"
)


@pytest.fixture
def api(tmp_path):

    pipeline = build_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    weather_rows = load_weather_intervals_csv(
        WEATHER
    )

    for index, item in enumerate(weather_rows):

        simulator.step(
            SolarIntervalInput(
                start_utc=item.start_utc,
                end_utc=item.end_utc,
                weather=item.weather,
                grid_available=(index != 2),
            )
        )

    db_path = tmp_path / "inverters.sqlite3"

    run_id = SolarHistorian(
        db_path
    ).save_simulation(
        simulator,
        scenario="GRID_LOSS",
        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    app = FastAPI()

    app.include_router(
        create_solar_inverter_history_router(
            db_path
        )
    )

    with TestClient(app) as client:
        yield client, run_id


def test_run_list_has_eight_inverter_records(api):

    client, run_id = api

    response = client.get(
        "/solar/inverters/runs"
    )

    assert response.status_code == 200

    run = next(
        row
        for row in response.json()
        if row["id"] == run_id
    )

    assert run["scenario"] == "GRID_LOSS"
    assert run["inverter_record_count"] == 8


def test_interval_details_and_filter(api):

    client, run_id = api

    base = (
        f"/solar/inverters/runs/{run_id}/intervals"
    )

    response = client.get(base)

    assert response.status_code == 200
    assert len(response.json()) == 8

    filtered = client.get(
        base,
        params={"inverter_id": "INV_1"},
    )

    assert filtered.status_code == 200
    assert len(filtered.json()) == 4

    assert all(
        row["inverter_id"] == "INV_1"
        for row in filtered.json()
    )

    assert all(
        isinstance(row["quality_flags"], list)
        for row in filtered.json()
    )


def test_grid_loss_and_alarm_scope(api):

    client, run_id = api

    base = f"/solar/inverters/runs/{run_id}"

    intervals = client.get(
        base + "/intervals"
    ).json()

    assert sum(
        row["ac_dispatched_kw"] == 0
        for row in intervals
    ) >= 2

    response = client.get(
        base + "/alarms"
    )

    assert response.status_code == 200

    grid_events = [
        row
        for row in response.json()
        if row["code"] == "GRID_UNAVAILABLE"
    ]

    assert len(grid_events) == 2

    assert all(
        row["source_table"] == "alarm_events"
        for row in grid_events
    )

    assert all(
        row["inverter_id"] is None
        for row in grid_events
    )


def test_snapshot_provenance_available(api):

    client, run_id = api

    response = client.get(
        f"/solar/inverters/runs/{run_id}/snapshots"
    )

    assert response.status_code == 200

    data = response.json()

    assert {
        row["component_id"]
        for row in data
    } == {
        "INV_1",
        "INV_2",
    }

    assert all(
        row["payload"]["values"][
            "inverter.nominal_efficiency"
        ]["value"] == 0.96
        for row in data
    )


def test_unknown_run_and_post_are_rejected(api):

    client, run_id = api

    assert client.get(
        "/solar/inverters/runs/999999/intervals"
    ).status_code == 404

    assert client.post(
        f"/solar/inverters/runs/{run_id}/intervals"
    ).status_code == 405


def test_dashboard_page_is_served(api):

    client, _ = api

    response = client.get(
        "/solar/inverters/dashboard"
    )

    assert response.status_code == 200

    assert (
        "GES İnverterleri"
        in response.text
    )


def test_missing_database_reports_503(tmp_path):

    app = FastAPI()

    app.include_router(
        create_solar_inverter_history_router(
            tmp_path / "missing.sqlite3"
        )
    )

    with TestClient(app) as client:

        assert client.get(
            "/solar/inverters/runs"
        ).status_code == 503


import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.solar_history_api import (
    create_solar_history_router,
)

from demo_ges_timeseries import run_demo


WEATHER_FILE = "data/solar/demo_weather_15m.csv"


@pytest.fixture
def api_client(tmp_path):

    output = tmp_path / "normal"

    # Create a real synthetic simulation record.
    run_demo(
        weather_file=WEATHER_FILE,
        output_directory=output,
    )

    app = FastAPI()

    app.include_router(
        create_solar_history_router(
            output / "historian.sqlite3"
        )
    )

    return TestClient(app)


def test_list_simulation_runs(api_client):

    response = api_client.get(
        "/solar/history/runs"
    )

    assert response.status_code == 200

    runs = response.json()

    assert len(runs) == 1
    assert runs[0]["scenario"] == "NORMAL"
    assert runs[0]["interval_count"] == 4


def test_read_production_intervals(api_client):

    response = api_client.get(
        "/solar/history/runs/1/intervals"
    )

    assert response.status_code == 200

    intervals = response.json()

    assert len(intervals) == 4

    assert intervals[-1]["cumulative_energy_kwh"] > 0

    assert isinstance(
        intervals[0]["source_types"],
        list,
    )


def test_normal_scenario_has_no_alarms(api_client):

    response = api_client.get(
        "/solar/history/runs/1/alarms"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_unknown_run_returns_404(api_client):

    response = api_client.get(
        "/solar/history/runs/999/intervals"
    )

    assert response.status_code == 404


def test_invalid_limit_returns_422(api_client):

    response = api_client.get(
        "/solar/history/runs/1/intervals?limit=0"
    )

    assert response.status_code == 422


def test_post_method_not_allowed(api_client):

    response = api_client.post(
        "/solar/history/runs"
    )

    assert response.status_code == 405


def test_missing_database_returns_503(tmp_path):

    database = tmp_path / "missing.sqlite3"

    app = FastAPI()

    app.include_router(
        create_solar_history_router(database)
    )

    client = TestClient(app)

    response = client.get(
        "/solar/history/runs"
    )

    assert response.status_code == 503
    assert not database.exists()


def test_grid_loss_alarm_history(tmp_path):

    output = tmp_path / "grid_loss"

    run_demo(
        weather_file=WEATHER_FILE,
        output_directory=output,
        grid_loss_interval_index=2,
    )

    app = FastAPI()

    app.include_router(
        create_solar_history_router(
            output / "historian.sqlite3"
        )
    )

    client = TestClient(app)

    response = client.get(
        "/solar/history/runs/1/alarms"
    )

    assert response.status_code == 200

    alarms = response.json()

    assert len(alarms) == 2

    assert alarms[0]["code"] == "GRID_UNAVAILABLE"
    assert alarms[0]["transition"] == "RAISED"

    assert alarms[1]["transition"] == "CLEARED"

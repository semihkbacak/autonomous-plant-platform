
"""Read-only simulator alarm center integration tests."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform_alarm_center import (
    create_platform_alarm_router,
)
from app.sim_runtime import SimulatorSessions
from simulator.hydro import HydroPlantSimulator
from simulator.scenarios import ScenarioType


def make_client():
    hydro = HydroPlantSimulator()
    hydro.set_auto_tick(False)

    sessions = SimulatorSessions()

    app = FastAPI()
    app.include_router(
        create_platform_alarm_router(hydro, sessions)
    )

    return TestClient(app), hydro, sessions


def test_empty_sources_healthy():
    client, _, _ = make_client()

    response = client.get(
        "/api/v1/platform/alarms/live"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["complete"]
    assert body["sources"] == {
        "HES": "AVAILABLE",
        "GES": "AVAILABLE",
        "RES": "AVAILABLE",
    }

    assert body["active_alarm_count"] == 0
    assert body["independent_simulation_clocks"]


def test_hes_grid_loss_is_simulator_alarm():
    client, hydro, _ = make_client()

    hydro.apply_scenario(
        ScenarioType.GRID_LOSS,
        seed=1,
    )

    data = client.get(
        "/api/v1/platform/alarms/live"
    ).json()

    assert any(
        alarm["plant"] == "HES"
        and alarm["code"] == "GRID_LOSS"
        for alarm in data["alarms"]
    )


def test_ges_mode_is_condition_not_alarm():
    client, _, sessions = make_client()

    sessions.ges.configure("GRID_LOSS")

    data = client.get(
        "/api/v1/platform/alarms/live"
    ).json()

    assert data["active_alarm_count"] == 0

    assert any(
        condition["plant"] == "GES"
        and condition["code"]
        == "SELECTED_SCENARIO_GRID_LOSS"
        for condition in data["conditions"]
    )


def test_res_model_error_is_alarm():
    client, _, sessions = make_client()

    sessions.res.error = "SyntheticStepFailed"

    data = client.get(
        "/api/v1/platform/alarms/live"
    ).json()

    assert any(
        alarm["plant"] == "RES"
        and alarm["code"] == "SIMULATION_MODEL_ERROR"
        for alarm in data["alarms"]
    )


def test_events_not_globally_ordered():
    client, _, sessions = make_client()

    sessions.ges.configure("LOW_LIGHT")
    sessions.res.configure("HIGH_WIND")

    response = client.get(
        "/api/v1/platform/alarms/events?limit=25"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["not_globally_time_ordered"]

    assert any(
        event["code"] == "MODE_LOW_LIGHT"
        for event in body["events_by_plant"]["GES"]
    )

    assert any(
        event["code"] == "MODE_HIGH_WIND"
        for event in body["events_by_plant"]["RES"]
    )


def test_invalid_limit_is_422():
    client, _, _ = make_client()

    response = client.get(
        "/api/v1/platform/alarms/events?limit=201"
    )

    assert response.status_code == 422


def test_alarm_page_is_read_only_and_has_links():
    client, _, _ = make_client()

    page = client.get("/platform/alarms")

    assert page.status_code == 200
    assert "Merkezi alarm" in page.text

    assert (
        "/api/v1/platform/alarms/live"
        in page.text
    )

    assert "/platform/dashboard" in page.text

    spec = client.get("/openapi.json").json()

    assert (
        "/api/v1/platform/alarms/live"
        in spec["paths"]
    )

    assert set(
        spec["paths"]["/api/v1/platform/alarms/live"]
    ) == {"get"}


def test_unavailable_source_is_explicit():
    client, _, sessions = make_client()

    original = sessions.session

    def failure(plant):
        if plant == "res":
            raise RuntimeError("test missing")

        return original(plant)

    sessions.session = failure

    data = client.get(
        "/api/v1/platform/alarms/live"
    ).json()

    assert not data["complete"]
    assert (
        data["sources"]["RES"]
        == "UNAVAILABLE"
    )

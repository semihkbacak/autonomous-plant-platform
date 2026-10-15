
"""HES live and historian ID regression tests."""
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from simulator.hydro import HydroPlantSimulator
from app.hydro_live_api import create_hydro_live_router
from app.hydro_analytics_api import (
    create_hydro_analytics_router,
)
from app.sim_runtime import SimulatorSessions
from app.sim_console_api import (
    create_sim_console_router,
)


@pytest.fixture()
def client(tmp_path):
    sim = HydroPlantSimulator()
    sim.set_auto_tick(False)

    api = FastAPI()

    api.include_router(
        create_hydro_live_router(sim)
    )

    api.include_router(
        create_hydro_analytics_router(
            tmp_path / "missing_hydro_history.sqlite3"
        )
    )

    api.include_router(
        create_sim_console_router(
            SimulatorSessions(),
            sim,
        )
    )

    return TestClient(api), sim


def test_live_unit_is_not_historian_run_id(client):
    http, _ = client

    response = http.get(
        "/api/v1/hes/live/units/UNIT_1"
    )

    assert response.status_code == 200
    assert response.json()["unit_id"] == "UNIT_1"

    assert response.json()["active_power_kw"] == (
        pytest.approx(0.0)
    )

    assert http.get(
        "/api/v1/hydro/runs/UNIT_1/units"
    ).status_code == 422


def test_live_list_has_two_units(client):
    http, _ = client

    data = http.get(
        "/api/v1/hes/live/units"
    ).json()

    assert data["scope"] == (
        "SYNTHETIC_LIVE_HES_READ_ONLY"
    )

    assert {
        unit["unit_id"]
        for unit in data["units"]
    } == {"UNIT_1", "UNIT_2"}


def test_unknown_live_unit_returns_404(client):
    http, _ = client

    assert http.get(
        "/api/v1/hes/live/units/UNIT_99"
    ).status_code == 404


def test_live_get_is_read_only(client):
    http, sim = client

    before = sim.snapshot()

    for _ in range(2):
        assert http.get(
            "/api/v1/hes/live/units/UNIT_1"
        ).status_code == 200

    after = sim.snapshot()

    assert before.simulation_time_s == (
        after.simulation_time_s
    )

    assert before.units[0].status == (
        after.units[0].status
    )


def test_console_writes_disabled_by_default(
    client, monkeypatch
):
    http, _ = client

    monkeypatch.delenv(
        "APP_SIM_CONSOLE_WRITES",
        raising=False,
    )

    response = http.post(
        "/api/v1/sim-console/hes/unit/start",
        json={"unit_id": "UNIT_1"},
        headers={
            "X-Sim-Console-Confirm": "SIMULATION_ONLY"
        },
    )

    assert response.status_code == 403


def test_console_start_with_opt_in(
    client, monkeypatch
):
    http, _ = client

    monkeypatch.setenv(
        "APP_SIM_CONSOLE_WRITES", "1"
    )

    response = http.post(
        "/api/v1/sim-console/hes/unit/start",
        json={"unit_id": "UNIT_1"},
        headers={
            "X-Sim-Console-Confirm": "SIMULATION_ONLY"
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True

    live = http.get(
        "/api/v1/hes/live/units/UNIT_1"
    ).json()

    assert live["status"] in (
        "STARTING", "RUNNING"
    )


def test_openapi_describes_live_unit_id(client):
    http, _ = client

    spec = http.get("/openapi.json").json()

    path = "/api/v1/hes/live/units/{unit_id}"

    assert path in spec["paths"]
    assert "UNIT_1" in str(spec["paths"][path])

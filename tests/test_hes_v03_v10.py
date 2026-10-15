"""HES staged v0.3-v1.0 acceptance tests. Simulator only."""
from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.hydro_analytics_api import create_hydro_analytics_router
from hes_v10_release import (
    acceptance,
    run_scenarios,
    verify_protective_scenarios,
)
from simulator.hydro import HydroPlantSimulator
from simulator.hydro_history import HydroHistorian
from simulator.hydro_safety_supervisor import HydroSimulationSupervisor
from simulator.hydro_suite import (
    CASES,
    annual_steady_state,
    run_dynamic_case,
)
from simulator.scenarios import ScenarioType


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    folder = tmp_path_factory.mktemp("hes_v10_matrix")
    data = run_scenarios(
        folder,
        seconds=60,
        sample_every=5,
    )
    return folder, data


def test_v03_historian_matrix_counts_energy(matrix):
    folder, manifest = matrix

    store = HydroHistorian.for_reading(
        folder / "hydro_history.sqlite3"
    )

    audit = store.audit(set(CASES))

    assert audit["passed"], audit["issues"]
    assert audit["run_count"] == len(CASES) == 12
    assert len(store.runs()) == 12

    run = next(
        r for r in store.runs()
        if r["scenario"] == "DUAL_UNIT"
    )

    summary = store.summary(run["id"])

    assert summary["energy_mwh"] > 0
    assert len(summary["unit_metrics"]) == 2

    assert sum(
        u["energy_mwh"]
        for u in summary["unit_metrics"]
    ) == pytest.approx(summary["energy_mwh"])


def test_v03_atomic_rollback_on_invalid_sample(tmp_path):
    db = HydroHistorian(tmp_path / "rollback.db")

    frames = run_dynamic_case(
        "BASELINE",
        seconds=20,
        sample_every=5,
    )

    invalid = deepcopy(frames)
    invalid[-1].units[0].active_power_mw = float("nan")

    with pytest.raises(ValueError, match="nonfinite"):
        db.save_run("BROKEN", invalid)

    assert db.runs() == []
    assert db.audit()["passed"]


def test_v03_rejects_timestamp_collision(tmp_path):
    db = HydroHistorian(tmp_path / "collision.db")

    frames = run_dynamic_case(
        "BASELINE",
        seconds=20,
        sample_every=5,
    )

    frames[-1] = deepcopy(frames[-2])

    with pytest.raises(ValueError, match="Non-monotonic"):
        db.save_run("BROKEN", frames)

    assert db.runs() == []


def test_v03_double_write_rejected_by_release(tmp_path):
    output = tmp_path / "matrix"

    run_scenarios(
        output,
        seconds=20,
        sample_every=5,
    )

    with pytest.raises(FileExistsError):
        run_scenarios(
            output,
            seconds=20,
            sample_every=5,
        )


def test_v04_api_and_dashboard(matrix):
    folder, _ = matrix

    app = FastAPI()

    app.include_router(
        create_hydro_analytics_router(
            folder / "hydro_history.sqlite3"
        )
    )

    client = TestClient(app)

    runs = client.get("/api/v1/hydro/runs")

    assert runs.status_code == 200
    assert len(runs.json()) == 12

    run_id = runs.json()[0]["id"]

    for suffix in (
        "samples",
        "units",
        "alarms",
        "summary",
    ):
        result = client.get(
            f"/api/v1/hydro/runs/{run_id}/{suffix}"
        )
        assert result.status_code == 200

    html = client.get("/hydro/dashboard")

    assert html.status_code == 200
    assert "<svg" in html.text
    assert "Canlı güç" in html.text

    assert client.get(
        "/api/v1/hydro/runs/999999/summary"
    ).status_code == 404


def test_v04_missing_db_does_not_create_file(tmp_path):
    path = tmp_path / "missing.db"
    app = FastAPI()

    app.include_router(
        create_hydro_analytics_router(path)
    )

    response = TestClient(app).get(
        "/api/v1/hydro/runs"
    )

    assert response.status_code == 503
    assert not path.exists()


def test_v05_governor_stats_and_alarm_events(matrix):
    folder, _ = matrix

    hist = HydroHistorian.for_reading(
        folder / "hydro_history.sqlite3"
    )

    power_step = next(
        r for r in hist.runs()
        if r["scenario"] == "POWER_STEP"
    )

    units = hist.summary(
        power_step["id"]
    )["unit_metrics"]

    assert any(
        u["governor_mae_mw"] is not None
        for u in units
    )

    grid = next(
        r for r in hist.runs()
        if r["scenario"] == "GRID_LOSS"
    )

    assert any(
        a["code"] == "GRID_LOSS"
        and a["transition"] == "RAISED"
        for a in hist.alarms(grid["id"])
    )


def test_v06_scenario_grid_recovery_closes_alarm(matrix):
    folder, _ = matrix

    hist = HydroHistorian.for_reading(
        folder / "hydro_history.sqlite3"
    )

    run = next(
        r for r in hist.runs()
        if r["scenario"] == "GRID_RECOVERY"
    )

    grid = [
        r for r in hist.alarms(run["id"])
        if r["code"] == "GRID_LOSS"
    ]

    assert [
        r["transition"]
        for r in grid
    ] == ["RAISED", "CLEARED"]


def test_v08_supervisor_grid_loss_trip():
    sim = HydroPlantSimulator()

    sim.request_start("UNIT_1")
    supervisor = HydroSimulationSupervisor()

    for _ in range(7):
        supervisor.guarded_tick(sim)

    assert sim.snapshot().units[0].active_power_mw > 0

    sim.apply_scenario(
        ScenarioType.GRID_LOSS
    )

    for _ in range(5):
        supervisor.guarded_tick(sim)

    assert sim.snapshot().emergency_stop
    assert sim.snapshot().units[0].active_power_mw == 0
    assert supervisor.latched_reason == "GRID_UNAVAILABLE"


def test_v08_supervisor_reset_requires_ack_and_healthy_state():
    sim = HydroPlantSimulator()
    guard = HydroSimulationSupervisor()

    sim.apply_scenario(
        ScenarioType.GRID_LOSS
    )

    guard.guarded_tick(sim)

    with pytest.raises(PermissionError):
        guard.reset(sim)

    with pytest.raises(
        ValueError,
        match="GRID_UNAVAILABLE",
    ):
        guard.reset(
            sim,
            operator_acknowledged=True,
        )

    sim.state.grid_available = True

    guard.reset(
        sim,
        operator_acknowledged=True,
    )

    assert guard.latched_reason is None
    assert not sim.snapshot().emergency_stop


def test_v08_supervisor_detects_malformed_signals():
    sim = HydroPlantSimulator()
    sim.state.units[0].rpm = float("nan")

    guard = HydroSimulationSupervisor()
    guard.guarded_tick(sim)

    assert guard.latched_reason == "NONFINITE_SENSOR_UNIT_1"


def test_v08_detects_energy_tampering(matrix, tmp_path):
    import shutil
    import sqlite3

    folder, _ = matrix
    altered = tmp_path / "tampered.db"

    shutil.copy2(
        folder / "hydro_history.sqlite3",
        altered,
    )

    with sqlite3.connect(altered) as conn:
        conn.execute(
            "UPDATE hydro_samples "
            "SET increment_mwh=increment_mwh+0.01 "
            "WHERE rowid=("
            "SELECT rowid FROM hydro_samples LIMIT 1)"
        )

    audit = HydroHistorian.for_reading(
        altered
    ).audit(set(CASES))

    assert not audit["passed"]

    assert any(
        issue.startswith("ENERGY_OR_TIMELINE")
        for issue in audit["issues"]
    )


def test_v09_annual_365_steady_state():
    result = annual_steady_state(days=365)

    assert result.intervals == 35040
    assert result.days == 365
    assert result.energy_mwh > 0

    assert (
        0 <= result.minimum_mw
        <= result.peak_mw
        <= 30
    )

    assert "NOT_DYNAMIC" in result.scope


def test_v09_invalid_days_rejected():
    for days in (0, 366, 2.3, True):
        with pytest.raises(ValueError):
            annual_steady_state(days=days)


def test_v10_release_requires_regression_and_full_year(matrix):
    folder, _ = matrix

    report = acceptance(
        folder / "hydro_history.sqlite3",
        annual_days=2,
    )

    assert not report["software_acceptance_passed"]

    assert (
        report["overall_status"]
        == "HES_CANDIDATE_INCOMPLETE"
    )

    assert report["v0.3_historian"]["passed"]
    assert report["oem_hydraulic_calibration"] is False
    assert report["real_site_validation"] is False


def test_v10_protective_scenario_outcomes(matrix):
    folder, _ = matrix

    result = verify_protective_scenarios(
        folder / "hydro_history.sqlite3"
    )

    assert result["passed"], result["issues"]
    assert len(result["checks"]) == 12
from fastapi.testclient import TestClient

import app.main as main_module
from simulator.hydro import HydroPlantSimulator


def create_test_client() -> TestClient:
    # Her test temiz bir HES simülatörüyle başlasın.
    main_module.sim = HydroPlantSimulator()
    return TestClient(main_module.app)


def start_unit(client: TestClient) -> None:
    response = client.post("/api/v1/units/UNIT_1/start")

    assert response.status_code == 200
    assert response.json()["accepted"] is True

    # STARTING -> RUNNING geçişi
    for _ in range(4):
        client.post("/api/v1/sim/tick")

    plant = client.get("/api/v1/plant").json()
    assert plant["units"][0]["status"] == "RUNNING"


def test_api_accepts_valid_power_setpoint():
    client = create_test_client()
    start_unit(client)

    response = client.post(
        "/api/v1/units/UNIT_1/power-setpoint",
        json={"target_power_mw": 8.0},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True

    plant = client.get("/api/v1/plant").json()
    unit = plant["units"][0]

    assert unit["power_setpoint_mw"] == 8.0


def test_api_blocks_excess_power_and_preserves_old_setpoint():
    client = create_test_client()
    start_unit(client)

    # Önce geçerli hedef.
    response = client.post(
        "/api/v1/units/UNIT_1/power-setpoint",
        json={"target_power_mw": 8.0},
    )

    assert response.json()["accepted"] is True

    # Sonra kapasiteyi aşan geçersiz hedef.
    response = client.post(
        "/api/v1/units/UNIT_1/power-setpoint",
        json={"target_power_mw": 25.0},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is False

    plant = client.get("/api/v1/plant").json()
    unit = plant["units"][0]

    # Reddedilen komut eski güvenli hedefi bozmamalı.
    assert unit["power_setpoint_mw"] == 8.0
def test_api_returns_active_grid_loss_alarm():
    client = create_test_client()

    main_module.sim.state.grid_available = False

    response = client.get("/api/v1/alarms/active")

    assert response.status_code == 200

    alarms = response.json()

    assert any(
        alarm["code"] == "GRID_LOSS"
        and alarm["severity"] == "CRITICAL"
        for alarm in alarms
    )
def test_api_alarm_history_is_initially_empty():
    client = create_test_client()

    response = client.get(
        "/api/v1/alarms/history"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_api_alarm_history_keeps_resolved_grid_loss():
    client = create_test_client()

    main_module.sim.state.grid_available = False

    client.post(
        "/api/v1/sim/tick"
    )

    main_module.sim.state.grid_available = True

    client.post(
        "/api/v1/sim/tick"
    )

    active_response = client.get(
        "/api/v1/alarms/active"
    )

    history_response = client.get(
        "/api/v1/alarms/history"
    )

    active = active_response.json()
    history = history_response.json()

    assert not any(
        alarm["code"] == "GRID_LOSS"
        for alarm in active
    )

    assert any(
        alarm["code"] == "GRID_LOSS"
        for alarm in history
    )


def test_api_can_apply_grid_loss_scenario():
    client = create_test_client()

    response = client.post(
        "/api/v1/sim/scenario",
        json={
            "scenario": "GRID_LOSS",
            "seed": 1,
        },
    )

    assert response.status_code == 200

    plant = response.json()

    assert plant["grid_available"] is False

    alarms = client.get(
        "/api/v1/alarms/active"
    ).json()

    assert any(
        alarm["code"] == "GRID_LOSS"
        for alarm in alarms
    )


def test_api_can_apply_high_vibration_scenario():
    client = create_test_client()

    response = client.post(
        "/api/v1/sim/scenario",
        json={
            "scenario": "HIGH_VIBRATION",
            "seed": 1,
        },
    )

    assert response.status_code == 200

    alarms = client.get(
        "/api/v1/alarms/active"
    ).json()

    assert any(
        alarm["code"] == "HIGH_VIBRATION"
        for alarm in alarms
    )
def test_api_returns_anomalies():
    client = create_test_client()

    main_module.sim.state.units[
        0
    ].bearing_temperature_c = 85.0

    response = client.get(
        "/api/v1/anomalies"
    )

    assert response.status_code == 200

    anomalies = response.json()

    assert any(
        item["code"]
        == "BEARING_TEMPERATURE_ANOMALY"
        for item in anomalies
    )


def test_api_returns_decisions():
    client = create_test_client()

    main_module.sim.state.grid_available = False

    response = client.get(
        "/api/v1/decisions"
    )

    assert response.status_code == 200

    decisions = response.json()

    assert any(
        item["action"]
        == "KEEP_GENERATION_BLOCKED"
        for item in decisions
    )
def test_api_returns_ml_anomaly():
    client = create_test_client()

    unit = (
        main_module.sim.state.units[0]
    )

    unit.status = "RUNNING"

    unit.active_power_mw = 12.0
    unit.bearing_temperature_c = 95.0
    unit.generator_temperature_c = 110.0
    unit.vibration_mm_s = 12.0
    unit.frequency_hz = 48.5
    unit.rpm = 700.0

    response = client.get(
        "/api/v1/ml/anomalies"
    )

    assert response.status_code == 200

    findings = response.json()

    assert len(findings) == 1

    assert (
        findings[0]["unit_id"]
        == "UNIT_1"
    )

    assert (
        findings[0]["is_anomaly"]
        is True
    )
def test_api_returns_system_assessment():
    client = create_test_client()

    response = client.get(
        "/api/v1/system/assessment"
    )

    assert response.status_code == 200

    data = response.json()

    assert "simulation_time_s" in data
    assert "total_active_power_mw" in data
    assert "active_alarms" in data
    assert "rule_anomalies" in data
    assert "ml_anomalies" in data
    assert "recommendations" in data


def test_system_assessment_contains_ml_anomaly():
    client = create_test_client()

    unit = (
        main_module.sim.state.units[0]
    )

    unit.status = "RUNNING"

    unit.active_power_mw = 12.0
    unit.bearing_temperature_c = 95.0
    unit.generator_temperature_c = 110.0
    unit.vibration_mm_s = 12.0
    unit.frequency_hz = 48.5
    unit.rpm = 700.0

    response = client.get(
        "/api/v1/system/assessment"
    )

    assert response.status_code == 200

    data = response.json()

    assert any(
        finding["is_anomaly"] is True
        for finding in data[
            "ml_anomalies"
        ]
    )

    assert any(
        decision["action"]
        == "REVIEW_ML_ANOMALY"
        for decision in data[
            "recommendations"
        ]
    )


def test_system_assessment_contains_plant_target():
    client = create_test_client()

    result = (
        main_module.sim.request_plant_power_target(
            20.0
        )
    )

    assert result.accepted is True

    response = client.get(
        "/api/v1/system/assessment"
    )

    assert response.status_code == 200

    data = response.json()

    assert (
        data["plant_power_target_mw"]
        == 20.0
    )
from core.alarms import detect_alarms
from core.anomaly import detect_anomalies
from core.decision import (
    build_decision_recommendations,
)
from simulator.hydro import (
    HydroPlantSimulator,
)


def test_normal_plant_has_no_anomalies():
    sim = HydroPlantSimulator()

    anomalies = detect_anomalies(
        sim.snapshot()
    )

    assert anomalies == []


def test_high_bearing_temperature_creates_anomaly():
    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    plant.units[
        0
    ].bearing_temperature_c = 85.0

    anomalies = detect_anomalies(
        plant
    )

    assert any(
        finding.code
        == "BEARING_TEMPERATURE_ANOMALY"
        and finding.unit_id == "UNIT_1"
        for finding in anomalies
    )


def test_high_vibration_creates_anomaly():
    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    plant.units[
        0
    ].vibration_mm_s = 9.0

    anomalies = detect_anomalies(
        plant
    )

    assert any(
        finding.code
        == "VIBRATION_ANOMALY"
        and finding.unit_id == "UNIT_1"
        for finding in anomalies
    )


def test_grid_loss_creates_critical_decision():
    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    plant.grid_available = False

    alarms = detect_alarms(
        plant
    )

    anomalies = detect_anomalies(
        plant
    )

    decisions = (
        build_decision_recommendations(
            plant=plant,
            alarms=alarms,
            anomalies=anomalies,
        )
    )

    assert any(
        decision.action
        == "KEEP_GENERATION_BLOCKED"
        and decision.priority
        == "CRITICAL"
        for decision in decisions
    )


def test_normal_plant_gets_continue_recommendation():
    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    decisions = (
        build_decision_recommendations(
            plant=plant,
            alarms=[],
            anomalies=[],
        )
    )

    assert any(
        decision.action
        == "CONTINUE_NORMAL_OPERATION"
        and decision.priority
        == "INFO"
        for decision in decisions
    )
def test_decision_engine_reacts_to_ml_anomaly():
    from core.models import MLAnomalyFinding

    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    ml_findings = [
        MLAnomalyFinding(
            unit_id="UNIT_1",
            is_anomaly=True,
            anomaly_score=0.95,
            model_name="IsolationForest",
        )
    ]

    decisions = (
        build_decision_recommendations(
            plant=plant,
            alarms=[],
            anomalies=[],
            ml_anomalies=ml_findings,
        )
    )

    assert any(
        decision.action
        == "REVIEW_ML_ANOMALY"
        and decision.priority
        == "CRITICAL"
        for decision in decisions
    )
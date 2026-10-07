from core.models import UnitStatus

from ml.anomaly_model import (
    evaluate_plant_with_model,
    evaluate_unit_with_model,
    generate_normal_training_rows,
    train_demo_anomaly_model,
)

from simulator.hydro import HydroPlantSimulator


def test_ml_training_data_has_expected_size():
    rows = generate_normal_training_rows(
        count=100,
        seed=42,
    )

    assert len(rows) == 100

    assert all(
        len(row) == 6
        for row in rows
    )


def test_ml_model_can_be_trained():
    model = train_demo_anomaly_model(
        seed=42
    )

    assert model is not None


def test_ml_detects_extreme_unit_anomaly():
    sim = HydroPlantSimulator()

    unit = sim.state.units[0]

    unit.status = UnitStatus.RUNNING
    unit.active_power_mw = 12.0
    unit.bearing_temperature_c = 95.0
    unit.generator_temperature_c = 110.0
    unit.vibration_mm_s = 12.0
    unit.frequency_hz = 48.5
    unit.rpm = 700.0

    model = train_demo_anomaly_model(
        seed=42
    )

    finding = evaluate_unit_with_model(
        unit=unit,
        model=model,
    )

    assert finding.is_anomaly is True

    assert finding.anomaly_score > 0.5


def test_ml_skips_stopped_units():
    sim = HydroPlantSimulator()

    findings = evaluate_plant_with_model(
        sim.snapshot()
    )

    assert findings == []
def test_normal_20_mw_dispatch_is_not_ml_anomaly():
    sim = HydroPlantSimulator()

    result = sim.request_plant_power_target(
        20.0
    )

    assert result.accepted is True

    for _ in range(15):
        sim.tick()

    findings = evaluate_plant_with_model(
        sim.snapshot()
    )

    assert len(findings) == 2

    assert all(
        finding.is_anomaly is False
        for finding in findings
    )
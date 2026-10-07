from core.alarms import detect_alarms
from simulator.hydro import HydroPlantSimulator


def test_normal_plant_has_no_alarms():
    sim = HydroPlantSimulator()

    alarms = detect_alarms(sim.snapshot())

    assert alarms == []


def test_grid_loss_creates_critical_alarm():
    sim = HydroPlantSimulator()
    plant = sim.snapshot()

    plant.grid_available = False

    alarms = detect_alarms(plant)

    assert any(
        alarm.code == "GRID_LOSS"
        and alarm.severity == "CRITICAL"
        for alarm in alarms
    )


def test_high_temperature_creates_alarm():
    sim = HydroPlantSimulator()
    plant = sim.snapshot()

    plant.units[0].bearing_temperature_c = 85.0

    alarms = detect_alarms(plant)

    assert any(
        alarm.code == "HIGH_BEARING_TEMPERATURE"
        and alarm.unit_id == "UNIT_1"
        for alarm in alarms
    )


def test_high_vibration_creates_alarm():
    sim = HydroPlantSimulator()
    plant = sim.snapshot()

    plant.units[0].vibration_mm_s = 9.0

    alarms = detect_alarms(plant)

    assert any(
        alarm.code == "HIGH_VIBRATION"
        and alarm.unit_id == "UNIT_1"
        for alarm in alarms
    )
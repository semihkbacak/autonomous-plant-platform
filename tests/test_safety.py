from simulator.hydro import HydroPlantSimulator
from core.safety import power_setpoint_permitted


def test_start_is_allowed_when_simulator_is_healthy():
    sim = HydroPlantSimulator()
    result = sim.request_start("UNIT_1")
    assert result.accepted is True


def test_start_is_blocked_by_emergency_stop():
    sim = HydroPlantSimulator()
    sim.set_emergency_stop(True)
    result = sim.request_start("UNIT_1")
    assert result.accepted is False
    assert "Emergency stop" in result.message


def test_start_is_blocked_by_maintenance_lock():
    sim = HydroPlantSimulator()
    sim.set_maintenance_lock(True)
    result = sim.request_start("UNIT_1")
    assert result.accepted is False
    assert "Maintenance lock" in result.message


def test_unit_reaches_running_after_ticks():
    sim = HydroPlantSimulator()
    result = sim.request_start("UNIT_1")
    assert result.accepted is True
    for _ in range(4):
        state = sim.tick()
    unit = next(u for u in state.units if u.unit_id == "UNIT_1")
    assert unit.status == "RUNNING"
    assert unit.active_power_mw > 0
    assert unit.rpm > 0
    assert unit.frequency_hz > 0


def test_running_unit_exposes_demo_process_signals():
    sim = HydroPlantSimulator()
    sim.request_start("UNIT_1")
    for _ in range(6):
        state = sim.tick()
    unit = next(u for u in state.units if u.unit_id == "UNIT_1")
    assert unit.active_power_mw > 0
    assert unit.reactive_power_mvar >= 0
    assert unit.voltage_kv > 0
    assert unit.current_a > 0
    assert unit.flow_m3_s > 0


def test_auto_tick_can_be_disabled():
    sim = HydroPlantSimulator()
    status = sim.set_auto_tick(False)
    assert status.auto_tick_enabled is False

def test_start_is_blocked_while_unit_is_stopping():
    sim = HydroPlantSimulator()

    start_result = sim.request_start("UNIT_1")
    assert start_result.accepted is True

    for _ in range(4):
        sim.tick()

    stop_result = sim.request_stop("UNIT_1")
    assert stop_result.accepted is True

    start_again_result = sim.request_start("UNIT_1")

    assert start_again_result.accepted is False
def test_power_setpoint_is_blocked_above_rated_power():
    sim = HydroPlantSimulator()

    sim.request_start("UNIT_1")

    for _ in range(4):
        sim.tick()

    plant = sim.snapshot()
    unit = plant.units[0]

    allowed, reasons = power_setpoint_permitted(
        plant,
        unit,
        target_power_mw=25.0,
    )

    assert allowed is False
    assert "Power target is out of range" in reasons
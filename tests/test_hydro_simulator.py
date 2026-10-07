import pytest

from core.models import UnitStatus
from simulator.hydro import HydroPlantSimulator
from simulator.hydro_physics import calculate_hydro_power_mw


def test_running_unit_power_matches_hydro_physics():
    sim = HydroPlantSimulator()

    start_result = sim.request_start("UNIT_1")
    assert start_result.accepted is True

    # 4 tick sonunda STARTING -> RUNNING olur.
    for _ in range(4):
        sim.tick()

    # Bir tick daha:
    # artık RUNNING bloğu gerçekten çalışsın.
    sim.tick()

    plant = sim.snapshot()
    unit = plant.units[0]

    assert unit.status == UnitStatus.RUNNING
    assert unit.flow_m3_s > 0.0

    expected_power_mw = calculate_hydro_power_mw(
        flow_m3_s=unit.flow_m3_s,
        net_head_m=plant.net_head_m,
        turbine_efficiency=unit.turbine_efficiency,
        generator_efficiency=unit.generator_efficiency,
    )

    assert unit.active_power_mw == pytest.approx(
        expected_power_mw,
        rel=0.001,
    )
def test_net_head_updates_from_gross_head_and_losses():
    sim = HydroPlantSimulator()

    sim.state.gross_head_m = 310.0
    sim.state.hydraulic_loss_m = 20.0

    sim.tick()

    plant = sim.snapshot()

    assert plant.net_head_m == 290.0
def test_running_needle_movement_is_rate_limited():
    sim = HydroPlantSimulator()

    sim.request_start("UNIT_1")

    for _ in range(4):
        sim.tick()

    # Test amacıyla needle'ı sıfıra çekiyoruz.
    sim.state.units[0].needle_opening_pct = 0.0

    sim.tick()

    unit = sim.snapshot().units[0]

    assert unit.status == UnitStatus.RUNNING

    assert unit.needle_opening_pct == pytest.approx(
        sim.MAX_NEEDLE_STEP_PCT_PER_TICK
    )
def test_governor_recovers_after_needle_closure():
    sim = HydroPlantSimulator()

    # Üniteyi başlat.
    start_result = sim.request_start("UNIT_1")
    assert start_result.accepted is True

    # 4 tick sonunda RUNNING durumuna geçsin.
    for _ in range(4):
        sim.tick()

    # Test için needle açıklığını sıfırla.
    sim.state.units[0].needle_opening_pct = 0.0

    errors = []

    # Governor tepkisini 20 tick boyunca izle.
    for step in range(1, 21):
        plant = sim.tick()
        unit = plant.units[0]

        error_mw = abs(
            unit.governor_target_power_mw
            - unit.active_power_mw
        )

        errors.append(error_mw)

        print(
            f"tick={step}, "
            f"needle={unit.needle_opening_pct:.1f}%, "
            f"target={unit.governor_target_power_mw:.2f} MW, "
            f"actual={unit.active_power_mw:.2f} MW, "
            f"error={error_mw:.2f} MW"
        )

    # Son güç hatası ilkinden küçük olmalı.
    assert errors[-1] < errors[0]

    # Demo için sonunda hata 0.5 MW altına inmeli.
    assert errors[-1] < 0.5
def test_governor_follows_operator_power_setpoint():
    sim = HydroPlantSimulator()

    # Üniteyi çalıştır.
    result = sim.request_start("UNIT_1")
    assert result.accepted is True

    for _ in range(4):
        sim.tick()

    # Operatörün 8 MW istediğini simüle et.
    sim.state.units[0].power_setpoint_mw = 8.0

    # Governor'a hedefe yaklaşması için zaman ver.
    for _ in range(20):
        sim.tick()

    unit = sim.snapshot().units[0]

    # Governor hedefi 8 MW olarak almalı.
    assert unit.governor_target_power_mw == pytest.approx(8.0)

    # Gerçekleşen güç hedefe yaklaşmalı.
    assert unit.active_power_mw == pytest.approx(
        8.0,
        abs=0.5,
    )
def test_power_setpoint_command_is_accepted():
    sim = HydroPlantSimulator()

    sim.request_start("UNIT_1")

    for _ in range(4):
        sim.tick()

    result = sim.request_power_setpoint(
        unit_id="UNIT_1",
        target_power_mw=8.0,
    )

    unit = sim.snapshot().units[0]

    assert result.accepted is True
    assert unit.power_setpoint_mw == 8.0
def test_power_setpoint_command_blocks_excess_power():
    sim = HydroPlantSimulator()

    sim.request_start("UNIT_1")

    for _ in range(4):
        sim.tick()

    result = sim.request_power_setpoint(
        unit_id="UNIT_1",
        target_power_mw=25.0,
    )

    unit = sim.snapshot().units[0]

    assert result.accepted is False
    assert unit.power_setpoint_mw is None
def test_simulator_has_no_active_alarms_initially():
    sim = HydroPlantSimulator()

    alarms = sim.active_alarms()

    assert alarms == []


def test_simulator_reports_active_grid_loss_alarm():
    sim = HydroPlantSimulator()

    sim.state.grid_available = False

    alarms = sim.active_alarms()

    assert any(
        alarm.code == "GRID_LOSS"
        for alarm in alarms
    )
def test_alarm_history_records_alarm_only_once():
    sim = HydroPlantSimulator()

    sim.state.grid_available = False

    sim.tick()
    sim.tick()

    history = sim.alarm_history()

    grid_loss_entries = [
        entry
        for entry in history
        if entry.code == "GRID_LOSS"
    ]

    assert len(grid_loss_entries) == 1


def test_resolved_alarm_remains_in_history():
    sim = HydroPlantSimulator()

    sim.state.grid_available = False
    sim.tick()

    sim.state.grid_available = True
    sim.tick()

    active = sim.active_alarms()
    history = sim.alarm_history()

    assert not any(
        alarm.code == "GRID_LOSS"
        for alarm in active
    )

    assert any(
        entry.code == "GRID_LOSS"
        for entry in history
    )
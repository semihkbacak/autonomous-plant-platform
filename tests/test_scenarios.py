from core.models import PlantState, UnitState
from simulator.scenarios import (
    ScenarioType,
    apply_plant_scenario,
    apply_demand_scenario,
    choose_random_scenario,
)

def test_grid_loss_scenario_marks_grid_unavailable():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
            ),
        ]
    )

    updated_plant = apply_plant_scenario(
        plant,
        ScenarioType.GRID_LOSS,
    )

    assert updated_plant.grid_available is False
    assert plant.grid_available is True

def test_unit_fault_scenario_faults_one_unit():
    plant = PlantState(
        units=[
            UnitState(unit_id="UNIT_1", rated_power_mw=15.0),
            UnitState(unit_id="UNIT_2", rated_power_mw=15.0),
        ]
    )

    updated_plant = apply_plant_scenario(
        plant,
        ScenarioType.UNIT_FAULT,
        seed=42,
    )

    faulted_units = [
        unit for unit in updated_plant.units
        if unit.fault
    ]

    assert len(faulted_units) == 1
    assert faulted_units[0].ready is False

def test_high_temperature_scenario_raises_temperature():
    plant = PlantState(
        units=[
            UnitState(unit_id="UNIT_1", rated_power_mw=15.0),
            UnitState(unit_id="UNIT_2", rated_power_mw=15.0),
        ]
    )

    updated_plant = apply_plant_scenario(
        plant,
        ScenarioType.HIGH_TEMPERATURE,
        seed=42,
    )

    temperatures = [
        unit.bearing_temperature_c
        for unit in updated_plant.units
    ]

    assert 85.0 in temperatures

def test_high_vibration_scenario_raises_vibration():
    plant = PlantState(
        units=[
            UnitState(unit_id="UNIT_1", rated_power_mw=15.0),
            UnitState(unit_id="UNIT_2", rated_power_mw=15.0),
        ]
    )

    updated_plant = apply_plant_scenario(
        plant,
        ScenarioType.HIGH_VIBRATION,
        seed=42,
    )

    vibrations = [
        unit.vibration_mm_s
        for unit in updated_plant.units
    ]

    assert 9.0 in vibrations

def test_low_headpond_scenario_reduces_water_level():
    plant = PlantState(
        units=[
            UnitState(unit_id="UNIT_1", rated_power_mw=15.0),
            UnitState(unit_id="UNIT_2", rated_power_mw=15.0),
        ]
    )

    updated_plant = apply_plant_scenario(
        plant,
        ScenarioType.LOW_HEADPOND,
    )

    assert updated_plant.headpond_level_pct == 15.0

def test_demand_increase_scenario_increases_target():
    original_target_mw = 20.0

    new_target_mw = apply_demand_scenario(
        original_target_mw,
        ScenarioType.DEMAND_INCREASE,
        seed=42,
    )

    assert new_target_mw > original_target_mw
    assert new_target_mw <= 30.0

def test_same_seed_produces_same_random_scenario():
    first = choose_random_scenario(seed=42)
    second = choose_random_scenario(seed=42)

    assert first == second
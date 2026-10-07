import pytest

from core.scheduler import (
    calculate_dispatch_setpoints,
    select_units_for_target,
)
from simulator.hydro import (
    HydroPlantSimulator,
)


def test_8_mw_target_requires_one_unit():
    sim = HydroPlantSimulator()

    selected = select_units_for_target(
        sim.snapshot(),
        8.0,
    )

    assert selected == [
        "UNIT_1"
    ]


def test_20_mw_target_requires_two_units():
    sim = HydroPlantSimulator()

    selected = select_units_for_target(
        sim.snapshot(),
        20.0,
    )

    assert selected == [
        "UNIT_1",
        "UNIT_2",
    ]


def test_20_mw_is_shared_between_two_equal_units():
    sim = HydroPlantSimulator()

    plant = sim.snapshot()

    selected = select_units_for_target(
        plant,
        20.0,
    )

    setpoints = (
        calculate_dispatch_setpoints(
            plant,
            20.0,
            selected,
        )
    )

    assert setpoints["UNIT_1"] == pytest.approx(
        10.0
    )

    assert setpoints["UNIT_2"] == pytest.approx(
        10.0
    )


def test_plant_target_above_capacity_is_blocked():
    sim = HydroPlantSimulator()

    result = sim.request_plant_power_target(
        40.0
    )

    assert result.accepted is False

    assert (
        sim.plant_power_target_mw
        is None
    )


def test_20_mw_plant_target_dispatches_two_units():
    sim = HydroPlantSimulator()

    result = sim.request_plant_power_target(
        20.0
    )

    assert result.accepted is True

    for _ in range(12):
        sim.tick()

    plant = sim.snapshot()

    unit_1 = plant.units[0]
    unit_2 = plant.units[1]

    assert unit_1.status == "RUNNING"
    assert unit_2.status == "RUNNING"

    assert (
        unit_1.power_setpoint_mw
        == pytest.approx(10.0)
    )

    assert (
        unit_2.power_setpoint_mw
        == pytest.approx(10.0)
    )

    assert (
        unit_1.active_power_mw
        == pytest.approx(
            10.0,
            abs=0.5,
        )
    )

    assert (
        unit_2.active_power_mw
        == pytest.approx(
            10.0,
            abs=0.5,
        )
    )
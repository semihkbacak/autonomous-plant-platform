
import pytest

from simulator.solar.inverter import InverterConfig
from simulator.solar.solar_plant import (
    SolarInverterInput,
    SolarPlantSimulator,
)


@pytest.fixture
def plant():
    configs = [
        InverterConfig(
            inverter_id="INV_1",
            rated_ac_kw=10.0,
            nominal_efficiency=0.96,
            mppt_min_v=200.0,
            mppt_max_v=800.0,
            max_dc_voltage_v=1000.0,
            max_dc_current_a=30.0,
        ),
        InverterConfig(
            inverter_id="INV_2",
            rated_ac_kw=10.0,
            nominal_efficiency=0.96,
            mppt_min_v=200.0,
            mppt_max_v=800.0,
            max_dc_voltage_v=1000.0,
            max_dc_current_a=30.0,
        ),
    ]

    return SolarPlantSimulator(configs)


@pytest.fixture
def normal_inputs():
    return [
        SolarInverterInput(
            inverter_id="INV_1",
            dc_power_kw=8.0,
            dc_voltage_v=400.0,
        ),
        SolarInverterInput(
            inverter_id="INV_2",
            dc_power_kw=8.0,
            dc_voltage_v=400.0,
        ),
    ]


def test_two_inverters_produce_power(
    plant, normal_inputs
):
    result = plant.simulate(normal_inputs)

    assert result.available_power_kw > 0
    assert result.dispatched_power_kw > 0
    assert len(result.inverter_results) == 2


def test_plant_meets_target(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        requested_target_kw=10.0,
    )

    assert result.dispatched_power_kw == pytest.approx(10.0)
    assert result.unserved_target_kw == pytest.approx(0.0)


def test_equal_inverters_share_target(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        requested_target_kw=8.0,
    )

    assert result.inverter_results[0].ac_dispatched_kw == pytest.approx(4.0)
    assert result.inverter_results[1].ac_dispatched_kw == pytest.approx(4.0)


def test_target_above_available_power(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        requested_target_kw=30.0,
    )

    assert result.dispatched_power_kw == pytest.approx(
        result.available_power_kw
    )
    assert result.unserved_target_kw > 0
    assert "INSUFFICIENT_AVAILABLE_POWER" in result.reasons


def test_operator_curtailment(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        requested_target_kw=5.0,
    )

    assert result.dispatched_power_kw == pytest.approx(5.0)
    assert result.curtailed_power_kw > 0
    assert "CURTAILMENT_APPLIED" in result.reasons


def test_grid_loss_blocks_plant(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        grid_available=False,
    )

    assert result.available_power_kw == 0
    assert result.dispatched_power_kw == 0
    assert "GRID_UNAVAILABLE" in result.reasons


def test_emergency_stop_blocks_plant(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        emergency_stop=True,
    )

    assert result.available_power_kw == 0
    assert result.dispatched_power_kw == 0
    assert "PLANT_EMERGENCY_STOP" in result.reasons


def test_one_faulty_inverter(
    plant
):
    inputs = [
        SolarInverterInput(
            inverter_id="INV_1",
            dc_power_kw=8.0,
            dc_voltage_v=400.0,
        ),
        SolarInverterInput(
            inverter_id="INV_2",
            dc_power_kw=8.0,
            dc_voltage_v=400.0,
            fault_active=True,
        ),
    ]

    result = plant.simulate(inputs)

    assert result.inverter_results[0].ac_dispatched_kw > 0
    assert result.inverter_results[1].ac_dispatched_kw == 0


def test_night_generation_is_zero(
    plant
):
    inputs = [
        SolarInverterInput("INV_1", 0.0, 0.0),
        SolarInverterInput("INV_2", 0.0, 0.0),
    ]

    result = plant.simulate(inputs)

    assert result.dispatched_power_kw == 0
    assert result.available_power_kw == 0


def test_zero_power_target(
    plant, normal_inputs
):
    result = plant.simulate(
        normal_inputs,
        requested_target_kw=0.0,
    )

    assert result.dispatched_power_kw == 0
    assert result.curtailed_power_kw > 0


def test_negative_target_rejected(
    plant, normal_inputs
):
    with pytest.raises(ValueError):
        plant.simulate(
            normal_inputs,
            requested_target_kw=-5.0,
        )


def test_missing_inverter_telemetry_rejected(
    plant
):
    inputs = [
        SolarInverterInput(
            "INV_1", 8.0, 400.0
        ),
    ]

    with pytest.raises(ValueError):
        plant.simulate(inputs)


def test_duplicate_telemetry_rejected(
    plant
):
    inputs = [
        SolarInverterInput("INV_1", 8.0, 400.0),
        SolarInverterInput("INV_1", 8.0, 400.0),
    ]

    with pytest.raises(ValueError):
        plant.simulate(inputs)


def test_unequal_inverters_get_unequal_dispatch(
    plant
):
    inputs = [
        SolarInverterInput("INV_1", 8.0, 400.0),
        SolarInverterInput("INV_2", 2.0, 400.0),
    ]

    result = plant.simulate(
        inputs,
        requested_target_kw=4.0,
    )

    power_1 = result.inverter_results[0].ac_dispatched_kw
    power_2 = result.inverter_results[1].ac_dispatched_kw

    assert power_1 > power_2
    assert power_1 + power_2 == pytest.approx(4.0)

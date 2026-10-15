
import math

import pytest

from simulator.solar.inverter import (
    InverterConfig,
    simulate_inverter,
)


@pytest.fixture
def inverter():
    # Synthetic demonstration inverter.
    return InverterConfig(
        inverter_id="INV_DEMO",
        rated_ac_kw=10.0,
        nominal_efficiency=0.96,
        mppt_min_v=200.0,
        mppt_max_v=800.0,
        max_dc_voltage_v=1000.0,
        max_dc_current_a=30.0,
    )


def test_night_has_zero_generation(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=0.0,
        dc_voltage_v=0.0,
    )

    assert result.status == "IDLE"
    assert result.ac_dispatched_kw == 0.0


def test_normal_dc_to_ac_conversion(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=400.0,
    )

    assert result.status == "RUNNING"
    assert 0 < result.ac_available_kw < 5.0


def test_ac_clipping(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=14.0,
        dc_voltage_v=400.0,
    )

    assert result.ac_available_kw == pytest.approx(10.0)
    assert result.clipping_loss_kw > 0
    assert "AC_CLIPPING" in result.reasons


def test_mppt_voltage_window(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=150.0,
    )

    assert result.status == "BLOCKED"
    assert "OUTSIDE_MPPT_WINDOW" in result.reasons


def test_dc_overvoltage(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=1100.0,
    )

    assert result.status == "BLOCKED"
    assert "DC_OVERVOLTAGE" in result.reasons


def test_dc_current_limit(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=20.0,
        dc_voltage_v=400.0,
    )

    assert result.dc_accepted_kw == pytest.approx(12.0)
    assert result.dc_rejected_kw == pytest.approx(8.0)
    assert "DC_CURRENT_LIMIT" in result.reasons


def test_grid_loss_blocks_generation(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=400.0,
        grid_available=False,
    )

    assert result.status == "BLOCKED"
    assert result.ac_dispatched_kw == 0.0


def test_inverter_fault_blocks_generation(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=400.0,
        fault_active=True,
    )

    assert result.status == "BLOCKED"


def test_maintenance_lock_blocks_generation(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=400.0,
        maintenance_lock=True,
    )

    assert result.status == "BLOCKED"


def test_operator_curtailment(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=8.0,
        dc_voltage_v=400.0,
        active_power_limit_kw=4.0,
    )

    assert result.ac_dispatched_kw == pytest.approx(4.0)
    assert result.curtailment_kw > 0
    assert "ACTIVE_POWER_LIMIT" in result.reasons


def test_zero_power_limit(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=400.0,
        active_power_limit_kw=0.0,
    )

    assert result.status == "CURTAILED"
    assert result.ac_dispatched_kw == 0.0


def test_negative_dc_power_is_rejected(inverter):
    with pytest.raises(ValueError):
        simulate_inverter(
            inverter,
            dc_power_kw=-1.0,
            dc_voltage_v=400.0,
        )


def test_nan_dc_power_is_rejected(inverter):
    with pytest.raises(ValueError):
        simulate_inverter(
            inverter,
            dc_power_kw=math.nan,
            dc_voltage_v=400.0,
        )


def test_invalid_voltage_measurement_blocks(inverter):
    result = simulate_inverter(
        inverter,
        dc_power_kw=5.0,
        dc_voltage_v=0.0,
    )

    assert result.status == "BLOCKED"


def test_invalid_inverter_configuration():
    with pytest.raises(ValueError):
        InverterConfig(
            inverter_id="BAD",
            rated_ac_kw=10.0,
            nominal_efficiency=0.96,
            mppt_min_v=200.0,
            mppt_max_v=1200.0,
            max_dc_voltage_v=1000.0,
            max_dc_current_a=30.0,
        )


def test_negative_power_limit_is_rejected(inverter):
    with pytest.raises(ValueError):
        simulate_inverter(
            inverter,
            dc_power_kw=5.0,
            dc_voltage_v=400.0,
            active_power_limit_kw=-2.0,
        )

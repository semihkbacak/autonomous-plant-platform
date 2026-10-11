import pytest

from simulator.solar_physics import (
    calculate_available_ac_power_kw,
    calculate_available_dc_power_kw,
    calculate_cell_temperature_c,
    calculate_deliverable_power_kw,
    calculate_interval_energy_kwh,
    calculate_temperature_factor,
    calculate_unserved_target_kw,
)


def test_zero_irradiance_produces_zero_dc_power():
    power = calculate_available_dc_power_kw(
        array_rated_power_kw=600.0,
        irradiance_w_m2=0.0,
        cell_temperature_c=25.0,
    )

    assert power == 0.0


def test_cell_temperature_increases_with_irradiance():
    temperature = calculate_cell_temperature_c(
        ambient_temperature_c=25.0,
        irradiance_w_m2=800.0,
    )

    assert temperature > 25.0


def test_high_cell_temperature_reduces_power_factor():
    factor = calculate_temperature_factor(
        cell_temperature_c=50.0,
    )

    assert factor < 1.0
    assert factor > 0.0


def test_standard_conditions_produce_rated_dc_power():
    power = calculate_available_dc_power_kw(
        array_rated_power_kw=500.0,
        irradiance_w_m2=1000.0,
        cell_temperature_c=25.0,
    )

    assert power == pytest.approx(
        500.0,
        rel=0.001,
    )


def test_inverter_efficiency_reduces_ac_power():
    power = calculate_available_ac_power_kw(
        available_dc_power_kw=500.0,
        inverter_rated_power_kw=500.0,
        inverter_efficiency=0.98,
    )

    assert power == pytest.approx(
        490.0,
        rel=0.001,
    )


def test_inverter_output_is_clipped_at_rated_power():
    power = calculate_available_ac_power_kw(
        available_dc_power_kw=700.0,
        inverter_rated_power_kw=500.0,
        inverter_efficiency=0.98,
    )

    assert power == 500.0


def test_target_is_limited_by_available_solar_power():
    deliverable = calculate_deliverable_power_kw(
        requested_target_kw=800.0,
        available_power_kw=530.0,
    )

    assert deliverable == 530.0


def test_target_below_available_power_is_respected():
    deliverable = calculate_deliverable_power_kw(
        requested_target_kw=400.0,
        available_power_kw=700.0,
    )

    assert deliverable == 400.0


def test_unserved_target_is_calculated():
    unserved = calculate_unserved_target_kw(
        requested_target_kw=800.0,
        deliverable_power_kw=530.0,
    )

    assert unserved == 270.0


def test_15_minute_energy_is_quarter_of_kw_value():
    energy = calculate_interval_energy_kwh(
        power_kw=800.0,
        interval_minutes=15.0,
    )

    assert energy == pytest.approx(
        200.0,
        rel=0.001,
    )


def test_negative_irradiance_is_rejected():
    with pytest.raises(ValueError):
        calculate_available_dc_power_kw(
            array_rated_power_kw=500.0,
            irradiance_w_m2=-1.0,
            cell_temperature_c=25.0,
        )
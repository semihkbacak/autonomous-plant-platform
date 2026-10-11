"""Stage 2: numerical/physical invariants for Faiman + De Soto.

These are not independent validation against real-world reference measurements.
"""

from datetime import datetime, timezone

import pytest

from simulator.solar.pv_array import (
    DeSotoModuleParameters,
    PVArrayConfiguration,
    calculate_pv_array_dc,
    calculate_pv_array_from_poa,
    synthetic_demo_module,
)
from simulator.solar.solar_resource import (
    IrradianceSample, PVSurface, SolarSite, calculate_poa,
)
from simulator.solar.solar_temperature import (
    FaimanParameters, calculate_pv_temperature,
)


def config(strings=2, modules=10, optical=1.0):
    return PVArrayConfiguration(
        modules_per_string=modules,
        parallel_strings=strings,
        module=synthetic_demo_module(),
        optical_transmission_factor=optical,
    )


def calc(poa=800, air=25, wind=2, cfg=None):
    return calculate_pv_array_dc(
        poa_global_w_m2=poa,
        ambient_temperature_c=air,
        wind_speed_m_s=wind,
        config=cfg if cfg is not None else config(),
    )


def test_zero_irradiance_yields_zero_dc_power():
    result = calc(poa=0)
    assert result.array_pmp_kw == 0
    assert result.module_pmp_w == 0


def test_stc_module_has_nonzero_mpp_and_iv_points():
    result = calc(poa=1000, air=25, wind=2)
    assert result.module_voc_v > result.module_vmp_v > 0
    assert result.module_isc_a > result.module_imp_a > 0
    assert result.module_pmp_w > 0


def test_mpp_is_consistent_with_voltage_times_current():
    result = calc()
    assert result.module_pmp_w == pytest.approx(
        result.module_vmp_v * result.module_imp_a, rel=1e-5
    )


def test_array_series_parallel_scaling():
    one = calc(cfg=config(strings=1, modules=1))
    bigger = calc(cfg=config(strings=3, modules=12))
    assert bigger.array_pmp_kw == pytest.approx(one.array_pmp_kw * 36, rel=1e-6)
    assert bigger.array_vmp_v == pytest.approx(one.module_vmp_v * 12, rel=1e-6)
    assert bigger.array_imp_a == pytest.approx(one.module_imp_a * 3, rel=1e-6)


def test_more_irradiance_increases_dc_power_in_demo_conditions():
    assert calc(poa=1000).array_pmp_kw > calc(poa=500).array_pmp_kw


def test_higher_ambient_temperature_reduces_dc_power_in_demo_conditions():
    assert calc(air=45).array_pmp_kw < calc(air=15).array_pmp_kw


def test_more_wind_reduces_faiman_module_temperature():
    slow = calculate_pv_temperature(800, 25, 1)
    fast = calculate_pv_temperature(800, 25, 8)
    assert fast.module_temperature_c < slow.module_temperature_c


def test_faiman_at_zero_irradiance_equals_ambient():
    temp = calculate_pv_temperature(0, 19, 2)
    assert temp.module_temperature_c == pytest.approx(19)
    assert temp.cell_temperature_c == pytest.approx(19)


def test_faiman_matches_formula_for_synthetic_coefficients():
    temp = calculate_pv_temperature(800, 25, 3, FaimanParameters(u0_w_m2_k=25, u1_w_s_m3_k=6.84))
    expected = 25 + 800 / (25 + 6.84 * 3)
    assert temp.module_temperature_c == pytest.approx(expected, rel=1e-10)


def test_optional_cell_module_offset_explicitly_changes_cell_only():
    baseline = calculate_pv_temperature(1000, 25, 2)
    adjusted = calculate_pv_temperature(1000, 25, 2, FaimanParameters(cell_over_module_c_at_1000w_m2=2.5))
    assert adjusted.module_temperature_c == pytest.approx(baseline.module_temperature_c)
    assert adjusted.cell_temperature_c == pytest.approx(baseline.cell_temperature_c + 2.5)


def test_lumped_optical_loss_factor_reduces_power():
    clear = calc(cfg=config(optical=1.0))
    reduced = calc(cfg=config(optical=0.7))
    assert reduced.array_pmp_kw < clear.array_pmp_kw


def test_optical_factor_zero_produces_zero_power():
    assert calc(cfg=config(optical=0)).array_pmp_kw == 0


def test_invalid_negative_irradiance_rejected():
    with pytest.raises(ValueError, match="poa_global_w_m2"):
        calc(poa=-1)


def test_invalid_config_rejected():
    with pytest.raises(ValueError, match="modules_per_string"):
        calc(cfg=config(modules=0))


def test_invalid_saturation_current_rejected():
    bad = DeSotoModuleParameters(
        alpha_sc_a_per_c=0.005, a_ref_v=2.0, i_l_ref_a=13.5,
        i_o_ref_a=0.0, r_sh_ref_ohm=400.0, r_s_ohm=0.3,
    )
    with pytest.raises(ValueError, match="i_o_ref_a"):
        calc(cfg=PVArrayConfiguration(10, 2, bad))


def test_night_from_poa_yields_zero_array_power():
    poa = calculate_poa(
        SolarSite(39.93, 32.86), PVSurface(30, 180),
        IrradianceSample(datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc), 0, 0, 0),
    )
    out = calculate_pv_array_from_poa(poa, 20.0, 3.0, config())
    assert out.array_pmp_kw == 0
    assert out.source_type == "SYNTHETIC"


def test_poa_quality_flags_are_propagated_not_hidden():
    poa = calculate_poa(
        SolarSite(39.93, 32.86), PVSurface(30, 180),
        IrradianceSample(datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc), 10, 0, 10),
    )
    out = calculate_pv_array_from_poa(poa, 20.0, 3.0, config())
    assert "NONZERO_IRRADIANCE_WHILE_SUN_BELOW_HORIZON" in out.source_quality_flags
    assert out.array_pmp_kw == 0


def test_invalid_wind_speed_rejected():
    with pytest.raises(ValueError, match="wind_speed_m_s"):
        calc(wind=-1)

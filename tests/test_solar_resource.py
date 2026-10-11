"""Science-facing invariants, not validation against measured PV data."""

from datetime import datetime, timezone

import pytest

from simulator.solar.solar_resource import (
    IrradianceSample,
    PVSurface,
    SolarSite,
    calculate_poa,
)


SITE = SolarSite(latitude_deg=39.93, longitude_deg=32.86)  # Demo coordinates, NOT a plant
SURFACE = PVSurface(tilt_deg=30, azimuth_deg=180, albedo=0.20)
NOON = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
NIGHT = datetime(2026, 6, 21, 0, 0, tzinfo=timezone.utc)


def observation(timestamp=NOON, ghi=800.0, dni=700.0, dhi=150.0):
    return IrradianceSample(timestamp, ghi, dni, dhi)


def test_sun_above_horizon_in_daytime():
    result = calculate_poa(SITE, SURFACE, observation())
    assert result.sun_above_horizon is True
    assert result.apparent_zenith_deg < 90.0
    assert result.poa_global_w_m2 > 0.0


def test_component_sum_equals_poa_global():
    result = calculate_poa(SITE, SURFACE, observation())
    component_sum = (
        result.poa_direct_w_m2
        + result.poa_sky_diffuse_w_m2
        + result.poa_ground_diffuse_w_m2
    )
    assert result.poa_global_w_m2 == pytest.approx(component_sum, abs=0.01)


def test_night_produces_zero_poa():
    result = calculate_poa(SITE, SURFACE, observation(NIGHT, 0, 0, 0))
    assert result.sun_above_horizon is False
    assert result.poa_global_w_m2 == 0.0


def test_night_with_nonzero_input_is_flagged():
    result = calculate_poa(SITE, SURFACE, observation(NIGHT, 10, 0, 10))
    assert result.poa_global_w_m2 == 0.0
    assert "NONZERO_IRRADIANCE_WHILE_SUN_BELOW_HORIZON" in result.quality_flags


def test_negative_irradiance_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_poa(SITE, SURFACE, observation(ghi=-1))


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_poa(SITE, SURFACE, observation(datetime(2026, 6, 21, 10)))


def test_invalid_geometry_rejected():
    with pytest.raises(ValueError, match="surface tilt"):
        calculate_poa(SITE, PVSurface(tilt_deg=110, azimuth_deg=180), observation())


def test_source_and_utc_preserved():
    result = calculate_poa(SITE, SURFACE, observation())
    assert result.source_type == "SYNTHETIC"
    assert result.timestamp_utc.tzinfo == timezone.utc


def test_invalid_source_rejected():
    with pytest.raises(ValueError, match="source_type"):
        calculate_poa(SITE, SURFACE, IrradianceSample(NOON, 500, 300, 150, "UNKNOWN"))

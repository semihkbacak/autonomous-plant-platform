
from datetime import datetime, timezone

import pytest

from simulator.solar.solar_resource import (
    IrradianceSample,
    PVSurface,
    SolarSite,
)

from simulator.solar.pv_array import (
    PVArrayConfiguration,
    synthetic_demo_module,
)

from simulator.solar.inverter import InverterConfig

from simulator.solar.solar_pipeline import (
    SolarAsset,
    SolarWeather,
    SolarPhysicsPipeline,
)


@pytest.fixture
def pipeline():

    module = synthetic_demo_module()

    assets = []

    for inverter_id in ("INV_1", "INV_2"):

        inverter = InverterConfig(
            inverter_id=inverter_id,
            rated_ac_kw=10.0,
            nominal_efficiency=0.96,
            mppt_min_v=200.0,
            mppt_max_v=800.0,
            max_dc_voltage_v=1000.0,
            max_dc_current_a=30.0,
        )

        array = PVArrayConfiguration(
            modules_per_string=10,
            parallel_strings=2,
            module=module,
        )

        assets.append(
            SolarAsset(
                inverter=inverter,
                array=array,
                surface=PVSurface(
                    tilt_deg=30.0,
                    azimuth_deg=180.0,
                ),
            )
        )

    return SolarPhysicsPipeline(
        site=SolarSite(
            latitude_deg=39.93,
            longitude_deg=32.86,
        ),
        assets=assets,
    )


@pytest.fixture
def daytime_weather():
    return SolarWeather(
        irradiance=IrradianceSample(
            timestamp=datetime(
                2026, 6, 21, 10, 0,
                tzinfo=timezone.utc,
            ),
            ghi_w_m2=800.0,
            dni_w_m2=700.0,
            dhi_w_m2=150.0,
        ),
        ambient_temperature_c=25.0,
        wind_speed_m_s=2.0,
    )


def test_daytime_produces_ac_power(
    pipeline, daytime_weather
):
    result = pipeline.simulate(daytime_weather)

    assert result.plant.available_power_kw > 0
    assert result.plant.dispatched_power_kw > 0
    assert len(result.array_reports) == 2


def test_array_dc_values_are_calculated(
    pipeline, daytime_weather
):
    result = pipeline.simulate(daytime_weather)

    for item in result.array_reports:
        assert item.poa.poa_global_w_m2 > 0
        assert item.dc.array_pmp_kw > 0
        assert item.dc.array_vmp_v > 0


def test_production_target_limits_power(
    pipeline, daytime_weather
):
    result = pipeline.simulate(
        daytime_weather,
        requested_target_kw=5.0,
    )

    assert result.plant.dispatched_power_kw == pytest.approx(
        5.0
    )
    assert result.plant.curtailed_power_kw > 0


def test_high_target_reports_shortfall(
    pipeline, daytime_weather
):
    result = pipeline.simulate(
        daytime_weather,
        requested_target_kw=100.0,
    )

    assert result.plant.unserved_target_kw > 0


def test_night_produces_zero_power(pipeline):

    weather = SolarWeather(
        irradiance=IrradianceSample(
            timestamp=datetime(
                2026, 6, 21, 0, 0,
                tzinfo=timezone.utc,
            ),
            ghi_w_m2=0.0,
            dni_w_m2=0.0,
            dhi_w_m2=0.0,
        ),
        ambient_temperature_c=20.0,
        wind_speed_m_s=2.0,
    )

    result = pipeline.simulate(weather)

    assert result.plant.available_power_kw == 0
    assert result.plant.dispatched_power_kw == 0


def test_grid_loss_blocks_generation(
    pipeline, daytime_weather
):
    result = pipeline.simulate(
        daytime_weather,
        grid_available=False,
    )

    assert result.plant.dispatched_power_kw == 0


def test_one_faulty_inverter(
    pipeline, daytime_weather
):
    result = pipeline.simulate(
        daytime_weather,
        fault_inverter_ids=frozenset({"INV_2"}),
    )

    inverters = result.plant.inverter_results

    assert inverters[0].ac_dispatched_kw > 0
    assert inverters[1].ac_dispatched_kw == 0


def test_unknown_inverter_is_rejected(
    pipeline, daytime_weather
):
    with pytest.raises(ValueError):
        pipeline.simulate(
            daytime_weather,
            fault_inverter_ids=frozenset({"INV_999"}),
        )


def test_invalid_wind_is_rejected(
    pipeline, daytime_weather
):
    invalid_weather = SolarWeather(
        irradiance=daytime_weather.irradiance,
        ambient_temperature_c=25.0,
        wind_speed_m_s=-1.0,
    )

    with pytest.raises(ValueError):
        pipeline.simulate(invalid_weather)


def test_source_type_is_preserved(
    pipeline, daytime_weather
):
    result = pipeline.simulate(daytime_weather)

    assert result.array_reports[0].dc.source_type == (
        "SYNTHETIC"
    )

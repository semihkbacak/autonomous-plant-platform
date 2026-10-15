
import csv

from datetime import (
    datetime,
    timedelta,
    timezone,
)

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

from simulator.solar.inverter import (
    InverterConfig,
)

from simulator.solar.solar_pipeline import (
    SolarAsset,
    SolarWeather,
    SolarPhysicsPipeline,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)


START = datetime(
    2026, 6, 21, 10, 0,
    tzinfo=timezone.utc,
)

STEP = timedelta(minutes=15)


@pytest.fixture
def simulator():

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

    pipeline = SolarPhysicsPipeline(
        site=SolarSite(
            latitude_deg=39.93,
            longitude_deg=32.86,
        ),
        assets=assets,
    )

    return SolarTimeSeriesSimulator(
        pipeline
    )


def make_interval(
    start=START,
    *,
    ghi=800.0,
    dni=700.0,
    dhi=150.0,
    target=None,
    grid=True,
    faults=frozenset(),
):

    end = start + STEP

    return SolarIntervalInput(
        start_utc=start,
        end_utc=end,

        weather=SolarWeather(
            irradiance=IrradianceSample(
                timestamp=end,
                ghi_w_m2=ghi,
                dni_w_m2=dni,
                dhi_w_m2=dhi,
            ),
            ambient_temperature_c=25.0,
            wind_speed_m_s=2.0,
        ),

        requested_target_kw=target,
        grid_available=grid,
        fault_inverter_ids=faults,
    )


def test_daytime_generates_energy(simulator):

    result = simulator.step(
        make_interval()
    )

    assert result.dispatched_power_kw > 0

    assert result.interval_energy_kwh == (
        pytest.approx(
            result.dispatched_power_kw * 0.25
        )
    )


def test_cumulative_energy_increases(simulator):

    first = simulator.step(
        make_interval()
    )

    second = simulator.step(
        make_interval(START + STEP)
    )

    assert second.cumulative_energy_kwh == (
        pytest.approx(
            first.interval_energy_kwh
            + second.interval_energy_kwh
        )
    )


def test_grid_loss_blocks_generation(simulator):

    result = simulator.step(
        make_interval(
            grid=False
        )
    )

    assert result.dispatched_power_kw == 0
    assert result.interval_energy_kwh == 0

    assert "GRID_UNAVAILABLE" in (
        result.active_alarms
    )


def test_grid_loss_raises_alarm(simulator):

    simulator.step(
        make_interval(grid=False)
    )

    history = simulator.alarm_history

    assert len(history) == 1
    assert history[0].code == "GRID_UNAVAILABLE"
    assert history[0].transition == "RAISED"


def test_persistent_alarm_is_not_duplicated(
    simulator,
):

    simulator.step(
        make_interval(grid=False)
    )

    simulator.step(
        make_interval(
            START + STEP,
            grid=False,
        )
    )

    assert len(simulator.alarm_history) == 1


def test_alarm_clears_when_grid_returns(
    simulator,
):

    simulator.step(
        make_interval(grid=False)
    )

    result = simulator.step(
        make_interval(
            START + STEP,
            grid=True,
        )
    )

    assert "GRID_UNAVAILABLE" not in (
        result.active_alarms
    )

    assert simulator.alarm_history[-1].transition == (
        "CLEARED"
    )


def test_inverter_fault_is_recorded(simulator):

    result = simulator.step(
        make_interval(
            faults=frozenset({"INV_2"}),
        )
    )

    assert "INVERTER_FAULT:INV_2" in (
        result.active_alarms
    )


def test_target_applies_curtailment(simulator):

    result = simulator.step(
        make_interval(target=5.0)
    )

    assert result.dispatched_power_kw == (
        pytest.approx(5.0)
    )

    assert result.curtailed_power_kw > 0


def test_time_gap_is_rejected(simulator):

    simulator.step(
        make_interval()
    )

    with pytest.raises(ValueError):
        simulator.step(
            make_interval(
                START + STEP * 2
            )
        )

    assert len(simulator.records) == 1


def test_incorrect_weather_timestamp_is_rejected(
    simulator,
):

    item = make_interval()

    incorrect_weather = SolarWeather(
        irradiance=IrradianceSample(
            timestamp=START,
            ghi_w_m2=800.0,
            dni_w_m2=700.0,
            dhi_w_m2=150.0,
        ),
        ambient_temperature_c=25.0,
        wind_speed_m_s=2.0,
    )

    invalid_item = SolarIntervalInput(
        start_utc=item.start_utc,
        end_utc=item.end_utc,
        weather=incorrect_weather,
    )

    with pytest.raises(ValueError):
        simulator.step(invalid_item)


def test_negative_irradiance_is_rejected(
    simulator,
):

    with pytest.raises(ValueError):
        simulator.step(
            make_interval(ghi=-10.0)
        )


def test_source_type_is_preserved(simulator):

    result = simulator.step(
        make_interval()
    )

    assert "SYNTHETIC" in result.source_types


def test_15_minute_csv_export(
    simulator,
    tmp_path,
):

    simulator.step(
        make_interval()
    )

    destination = (
        tmp_path / "production_15m.csv"
    )

    simulator.export_15m_csv(
        destination
    )

    with destination.open(
        encoding="utf-8",
        newline="",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    assert len(rows) == 1
    assert "interval_energy_kwh" in rows[0]
    assert rows[0]["start_utc"].startswith(
        "2026-06-21T10:00:00"
    )


def test_hourly_csv_partial_coverage(
    simulator,
    tmp_path,
):

    simulator.step(
        make_interval()
    )

    simulator.step(
        make_interval(
            START + STEP
        )
    )

    destination = (
        tmp_path / "production_hourly.csv"
    )

    simulator.export_hourly_csv(
        destination
    )

    with destination.open(
        encoding="utf-8",
        newline="",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    assert len(rows) == 1
    assert rows[0]["interval_count"] == "2"
    assert rows[0]["coverage_minutes"] == "30"

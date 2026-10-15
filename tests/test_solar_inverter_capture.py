
from pathlib import Path

import pytest

from demo_ges_timeseries import build_demo_pipeline

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)


WEATHER_FILE = (
    Path(__file__).resolve().parents[1]
    / "data/solar/demo_weather_15m.csv"
)


def make_simulation_result(
    grid_available: bool = True,
):
    # Read one valid synthetic weather interval.
    weather_row = load_weather_intervals_csv(
        WEATHER_FILE
    )[0]

    # Build the existing two-inverter GES.
    simulator = SolarTimeSeriesSimulator(
        build_demo_pipeline()
    )

    # Run a 15-minute interval.
    result = simulator.step(
        SolarIntervalInput(
            start_utc=weather_row.start_utc,
            end_utc=weather_row.end_utc,
            weather=weather_row.weather,
            grid_available=grid_available,
        )
    )

    return result


def test_both_inverters_are_recorded():

    result = make_simulation_result()

    assert len(result.inverter_results) == 2

    inverter_ids = {
        inverter.inverter_id
        for inverter in result.inverter_results
    }

    assert inverter_ids == {"INV_1", "INV_2"}

    total_power = sum(
        inverter.ac_dispatched_kw
        for inverter in result.inverter_results
    )

    assert total_power == pytest.approx(
        result.dispatched_power_kw
    )


def test_grid_loss_blocks_inverter_dispatch():

    result = make_simulation_result(
        grid_available=False
    )

    assert len(result.inverter_results) == 2

    assert result.dispatched_power_kw == 0

    assert all(
        inverter.ac_dispatched_kw == 0
        for inverter in result.inverter_results
    )

    assert "GRID_UNAVAILABLE" in result.active_alarms

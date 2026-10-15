from pathlib import Path
from unittest.mock import patch

from demo_ges_timeseries import build_demo_pipeline
from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)
import simulator.solar.solar_pipeline as solar_pipeline


WEATHER = (
    Path(__file__).resolve().parents[1]
    / "data/solar/demo_weather_15m.csv"
)


def test_identical_arrays_share_one_physics_calculation():
    pipeline = build_demo_pipeline()
    weather = load_weather_intervals_csv(WEATHER)[0].weather

    original_poa = solar_pipeline.calculate_poa
    original_dc = solar_pipeline.calculate_pv_array_from_poa

    with (
        patch.object(
            solar_pipeline,
            "calculate_poa",
            wraps=original_poa,
        ) as poa_spy,
        patch.object(
            solar_pipeline,
            "calculate_pv_array_from_poa",
            wraps=original_dc,
        ) as dc_spy,
    ):
        result = pipeline.simulate(weather)

    assert len(result.plant.inverter_results) == 2
    assert poa_spy.call_count == 1
    assert dc_spy.call_count == 1
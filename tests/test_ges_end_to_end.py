
import csv

import pytest

from demo_ges_timeseries import run_demo


WEATHER_FILE = "data/solar/demo_weather_15m.csv"


def test_normal_ges_demo(tmp_path):

    sim = run_demo(
        weather_file=WEATHER_FILE,
        output_directory=tmp_path / "normal",
    )

    assert len(sim.records) == 4

    assert sim.records[-1].cumulative_energy_kwh > 0

    assert all(
        record.dispatched_power_kw >= 0
        for record in sim.records
    )

    assert len(sim.alarm_history) == 0


def test_grid_loss_scenario(tmp_path):

    sim = run_demo(
        weather_file=WEATHER_FILE,
        output_directory=tmp_path / "grid_loss",
        grid_loss_interval_index=2,
    )

    assert len(sim.records) == 4

    assert sim.records[2].dispatched_power_kw == 0

    assert sim.records[2].interval_energy_kwh == 0

    events = [
        event
        for event in sim.alarm_history
        if event.code == "GRID_UNAVAILABLE"
    ]

    assert len(events) == 2

    assert events[0].transition == "RAISED"
    assert events[1].transition == "CLEARED"


def test_energy_and_csv_are_consistent(tmp_path):

    output = tmp_path / "normal"

    sim = run_demo(
        weather_file=WEATHER_FILE,
        output_directory=output,
    )

    with (output / "production_15m.csv").open(
        encoding="utf-8",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 4

    csv_energy = sum(
        float(row["interval_energy_kwh"])
        for row in rows
    )

    assert csv_energy == pytest.approx(
        sim.records[-1].cumulative_energy_kwh
    )

    with (output / "production_hourly.csv").open(
        encoding="utf-8",
        newline="",
    ) as file:
        hourly = list(csv.DictReader(file))

    assert len(hourly) == 1

    assert hourly[0]["interval_count"] == "4"
    assert hourly[0]["coverage_minutes"] == "60"

    assert float(hourly[0]["energy_kwh"]) == (
        pytest.approx(csv_energy)
    )


def test_invalid_grid_loss_index(tmp_path):

    with pytest.raises(ValueError):
        run_demo(
            weather_file=WEATHER_FILE,
            output_directory=tmp_path,
            grid_loss_interval_index=99,
        )
def test_demo_saves_historian(tmp_path):
    from simulator.solar.historian import SolarHistorian

    output = tmp_path / "historian_integration"

    simulation = run_demo(
        weather_file=WEATHER_FILE,
        output_directory=output,
    )

    historian = SolarHistorian(
        output / "historian.sqlite3"
    )

    runs = historian.list_runs()

    assert len(runs) == 1
    assert runs[0]["scenario"] == "NORMAL"

    records = historian.get_intervals(runs[0]["id"])

    assert len(records) == len(simulation.records)
    assert len(records) == 4
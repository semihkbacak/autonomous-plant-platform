
import sqlite3

import pytest

from demo_ges_timeseries import (
    build_demo_pipeline,
    run_demo,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)


WEATHER_FILE = "data/solar/demo_weather_15m.csv"


@pytest.fixture
def normal_simulation(tmp_path):
    return run_demo(
        weather_file=WEATHER_FILE,
        output_directory=tmp_path / "normal",
    )


def test_save_and_reopen_database(
    tmp_path,
    normal_simulation,
):
    path = tmp_path / "historian.sqlite3"

    historian = SolarHistorian(path)

    run_id = historian.save_simulation(
        normal_simulation,
        scenario="NORMAL",
    )

    # Reopen the database to verify persistence.
    reopened = SolarHistorian(path)

    runs = reopened.list_runs()
    intervals = reopened.get_intervals(run_id)

    assert len(runs) == 1
    assert runs[0]["scenario"] == "NORMAL"
    assert runs[0]["interval_count"] == 4

    assert len(intervals) == 4

    assert runs[0]["total_energy_kwh"] == pytest.approx(
        normal_simulation.records[-1].cumulative_energy_kwh
    )


def test_grid_loss_alarm_history(tmp_path):
    simulation = run_demo(
        weather_file=WEATHER_FILE,
        output_directory=tmp_path / "grid_loss",
        grid_loss_interval_index=2,
    )

    historian = SolarHistorian(
        tmp_path / "alarms.sqlite3"
    )

    run_id = historian.save_simulation(
        simulation,
        scenario="GRID_LOSS",
    )

    events = historian.get_alarms(run_id)
    intervals = historian.get_intervals(run_id)

    assert len(events) == 2

    assert events[0]["code"] == "GRID_UNAVAILABLE"
    assert events[0]["transition"] == "RAISED"

    assert events[1]["code"] == "GRID_UNAVAILABLE"
    assert events[1]["transition"] == "CLEARED"

    assert intervals[2]["dispatched_power_kw"] == 0


def test_multiple_runs_are_separate(
    tmp_path,
    normal_simulation,
):
    historian = SolarHistorian(
        tmp_path / "multiple.sqlite3"
    )

    first_id = historian.save_simulation(
        normal_simulation,
        scenario="RUN_1",
    )

    second_id = historian.save_simulation(
        normal_simulation,
        scenario="RUN_2",
    )

    assert first_id != second_id
    assert len(historian.list_runs()) == 2

    assert len(historian.get_intervals(first_id)) == 4
    assert len(historian.get_intervals(second_id)) == 4


def test_empty_simulation_is_rejected(tmp_path):
    simulation = SolarTimeSeriesSimulator(
        build_demo_pipeline()
    )

    historian = SolarHistorian(
        tmp_path / "empty.sqlite3"
    )

    with pytest.raises(ValueError):
        historian.save_simulation(simulation)

    assert historian.list_runs() == []


def test_empty_scenario_is_rejected(
    tmp_path,
    normal_simulation,
):
    historian = SolarHistorian(
        tmp_path / "scenario.sqlite3"
    )

    with pytest.raises(ValueError):
        historian.save_simulation(
            normal_simulation,
            scenario=" ",
        )

    assert historian.list_runs() == []


def test_failed_transaction_rolls_back(
    tmp_path,
    normal_simulation,
):
    historian = SolarHistorian(
        tmp_path / "rollback.sqlite3"
    )

    # Duplicate the first time interval.
    # The database PRIMARY KEY must reject it.
    normal_simulation.records.append(
        normal_simulation.records[0]
    )

    with pytest.raises(sqlite3.IntegrityError):
        historian.save_simulation(
            normal_simulation,
            scenario="BAD_RUN",
        )

    # The failed run must not be partially saved.
    assert historian.list_runs() == []


import sqlite3

import pytest

from pathlib import Path

from demo_ges_timeseries import build_demo_pipeline

from simulator.solar.historian import SolarHistorian

from simulator.solar.inverter_snapshot_payloads import (
    build_demo_inverter_snapshot_payloads,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


WEATHER = (
    Path(__file__).resolve().parents[1]
    / "data/solar/demo_weather_15m.csv"
)


def make_simulator(grid_loss_index=None):

    pipeline = build_demo_pipeline()
    simulator = SolarTimeSeriesSimulator(pipeline)

    weather_rows = load_weather_intervals_csv(
        WEATHER
    )

    for index, item in enumerate(weather_rows):
        simulator.step(
            SolarIntervalInput(
                start_utc=item.start_utc,
                end_utc=item.end_utc,
                weather=item.weather,
                grid_available=(
                    index != grid_loss_index
                ),
            )
        )

    return simulator, pipeline


def test_snapshot_uses_demo_configuration():

    pipeline = build_demo_pipeline()

    payloads = (
        build_demo_inverter_snapshot_payloads(
            pipeline
        )
    )

    assert set(payloads) == {"INV_1", "INV_2"}

    for inverter_id, payload in payloads.items():

        assert payload["component_id"] == inverter_id

        assert payload["values"][
            "inverter.rated_ac_kw"
        ]["value"] == 10.0

        assert payload["values"][
            "inverter.nominal_efficiency"
        ]["value"] == 0.96

        assert payload["values"][
            "array.modules_per_string"
        ]["value"] == 10

        assert payload["values"][
            "array.parallel_strings"
        ]["value"] == 2


def test_normal_run_writes_both_inverters(tmp_path):

    simulator, pipeline = make_simulator()

    path = tmp_path / "normal.sqlite3"

    historian = SolarHistorian(path)

    run_id = historian.save_simulation(
        simulator,
        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    with sqlite3.connect(path) as db:

        count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        assert count == len(simulator.records) * 2

        comparisons = db.execute(
            """
            SELECT
                p.dispatched_power_kw,
                SUM(i.ac_dispatched_kw)
            FROM production_intervals AS p
            JOIN ges_inverter_intervals AS i
              ON i.run_id = p.run_id
             AND i.start_utc = p.start_utc
            WHERE p.run_id = ?
            GROUP BY p.start_utc
            ORDER BY p.start_utc
            """,
            (run_id,),
        ).fetchall()

        assert len(comparisons) == len(
            simulator.records
        )

        for plant_power, inverter_sum in comparisons:
            assert inverter_sum == pytest.approx(
                plant_power,
                abs=1e-6,
            )

        snapshots = db.execute(
            "SELECT COUNT(*) "
            "FROM ges_parameter_snapshots"
        ).fetchone()[0]

        assert snapshots == 2


def test_grid_loss_keeps_plant_alarm_scope(tmp_path):

    simulator, pipeline = make_simulator(
        grid_loss_index=2
    )

    path = tmp_path / "grid_loss.sqlite3"

    historian = SolarHistorian(path)

    run_id = historian.save_simulation(
        simulator,
        scenario="GRID_LOSS",
        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    with sqlite3.connect(path) as db:

        # Grid-loss interval is the third record.
        start = simulator.records[2].start_utc.isoformat()

        inverter_powers = db.execute(
            """
            SELECT ac_dispatched_kw
            FROM ges_inverter_intervals
            WHERE run_id = ?
              AND start_utc = ?
            """,
            (run_id, start),
        ).fetchall()

        assert len(inverter_powers) == 2
        assert all(power[0] == 0 for power in inverter_powers)

        plant_alarm_count = db.execute(
            """
            SELECT COUNT(*)
            FROM alarm_events
            WHERE run_id = ?
              AND code = 'GRID_UNAVAILABLE'
            """,
            (run_id,),
        ).fetchone()[0]

        assert plant_alarm_count >= 1

        inverter_alarm_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_inverter_alarm_events
            WHERE run_id = ?
              AND code = 'GRID_UNAVAILABLE'
            """,
            (run_id,),
        ).fetchone()[0]

        assert inverter_alarm_count == 0


def test_legacy_save_remains_supported(tmp_path):

    simulator, _ = make_simulator()

    path = tmp_path / "legacy.sqlite3"

    historian = SolarHistorian(path)

    run_id = historian.save_simulation(
        simulator
    )

    with sqlite3.connect(path) as db:

        plant_count = db.execute(
            "SELECT COUNT(*) "
            "FROM production_intervals "
            "WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]

        inverter_count = db.execute(
            "SELECT COUNT(*) "
            "FROM ges_inverter_intervals "
            "WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]

        assert plant_count == len(simulator.records)
        assert inverter_count == 0

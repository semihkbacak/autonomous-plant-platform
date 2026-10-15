
import sqlite3

from simulator.solar.historian import SolarHistorian


def test_solar_historian_creates_inverter_tables(tmp_path):
    path = tmp_path / "historian.sqlite3"

    SolarHistorian(path)

    with sqlite3.connect(path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table'"
            )
        }

        assert {
            "simulation_runs",
            "production_intervals",
            "alarm_events",
            "ges_parameter_snapshots",
            "ges_inverter_intervals",
            "ges_inverter_alarm_events",
        }.issubset(tables)

        foreign_tables = {
            row[2]
            for row in db.execute(
                "PRAGMA foreign_key_list("
                "ges_inverter_intervals)"
            )
        }

        assert "production_intervals" in foreign_tables
        assert "ges_parameter_snapshots" in foreign_tables


def test_reopening_historian_keeps_existing_runs(tmp_path):
    path = tmp_path / "historian.sqlite3"

    SolarHistorian(path)

    with sqlite3.connect(path) as db:
        db.execute(
            """
            INSERT INTO simulation_runs (
                scenario,
                created_at_utc,
                interval_count,
                total_energy_kwh
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "HISTORY_PRESERVATION_TEST",
                "2026-06-21T10:00:00+00:00",
                1,
                2.5,
            ),
        )
        db.commit()

    # Initializing again must not destroy history.
    SolarHistorian(path)

    with sqlite3.connect(path) as db:
        result = db.execute(
            """
            SELECT scenario, total_energy_kwh
            FROM simulation_runs
            """
        ).fetchone()

        assert result == (
            "HISTORY_PRESERVATION_TEST",
            2.5,
        )

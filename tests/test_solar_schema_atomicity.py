
import sqlite3

import pytest

from simulator.solar.historian import SolarHistorian


def test_schema_creation_is_atomic(
    tmp_path,
    monkeypatch,
):
    """
    Simulate a migration failure after some
    tables have already been created.

    No partially initialized schema should remain.
    """

    database = tmp_path / "atomic.sqlite3"

    def simulate_migration_failure(db):
        db.execute(
            """
            CREATE TABLE ges_inverter_partial_test (
                id INTEGER PRIMARY KEY
            )
            """
        )

        raise RuntimeError(
            "SIMULATED_SCHEMA_FAILURE"
        )

    monkeypatch.setattr(
        "simulator.solar.historian."
        "initialize_ges_inverter_schema",
        simulate_migration_failure,
    )

    with pytest.raises(
        RuntimeError,
        match="SIMULATED_SCHEMA_FAILURE",
    ):
        SolarHistorian(database)

    with sqlite3.connect(database) as db:

        tables = {
            row[0]
            for row in db.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert "simulation_runs" not in tables
    assert "production_intervals" not in tables
    assert "alarm_events" not in tables
    assert "ges_inverter_partial_test" not in tables


import sqlite3

import pytest

from simulator.solar.historian import (
    SolarHistorian,
)


def test_failed_schema_creation_rolls_back(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "atomic.sqlite3"

    def broken_migration(db):
        db.execute(
            "CREATE TABLE test_partial(id INTEGER)"
        )
        raise RuntimeError("EXPECTED_MIGRATION_FAILURE")

    monkeypatch.setattr(
        "simulator.solar.historian."
        "initialize_ges_inverter_schema",
        broken_migration,
    )

    with pytest.raises(
        RuntimeError,
        match="EXPECTED_MIGRATION_FAILURE",
    ):
        SolarHistorian(path)

    with sqlite3.connect(path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

    assert "simulation_runs" not in tables
    assert "production_intervals" not in tables
    assert "alarm_events" not in tables
    assert "test_partial" not in tables

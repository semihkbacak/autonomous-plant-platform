
import sqlite3

import pytest

from simulator.solar.inverter_history_schema import (
    initialize_ges_inverter_schema,
)


def create_demo_db():
    db = sqlite3.connect(":memory:")

    db.execute("PRAGMA foreign_keys=ON")

    db.execute(
        "CREATE TABLE production_intervals ("
        "run_id INTEGER NOT NULL, "
        "start_utc TEXT NOT NULL, "
        "available_power_kw REAL, "
        "dispatched_power_kw REAL, "
        "interval_energy_kwh REAL, "
        "PRIMARY KEY(run_id, start_utc))"
    )

    db.execute(
        "CREATE TABLE hes_sentinel (value TEXT)"
    )

    db.execute(
        "INSERT INTO hes_sentinel "
        "VALUES ('unchanged')"
    )

    db.commit()
    return db


def test_three_ges_tables_created():

    with create_demo_db() as db:
        initialize_ges_inverter_schema(db)

        names = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        assert {
            "ges_parameter_snapshots",
            "ges_inverter_intervals",
            "ges_inverter_alarm_events",
        } <= names

        assert db.execute(
            "SELECT value FROM hes_sentinel"
        ).fetchone() == ("unchanged",)


def test_migration_is_idempotent():

    with create_demo_db() as db:
        initialize_ges_inverter_schema(db)

        db.execute(
            "INSERT INTO ges_parameter_snapshots "
            "VALUES (?, ?, ?, ?)",
            (
                "sample-hash",
                "TEST_PANEL",
                "synthetic",
                "{}",
            ),
        )

        initialize_ges_inverter_schema(db)

        assert db.execute(
            "SELECT count(*) "
            "FROM ges_parameter_snapshots"
        ).fetchone()[0] == 1


def test_requires_foreign_keys():

    db = create_demo_db()

    try:
        db.execute(
            "PRAGMA foreign_keys=OFF"
        )

        with pytest.raises(
            ValueError,
            match="foreign_keys",
        ):
            initialize_ges_inverter_schema(db)

    finally:
        db.close()


def test_rejects_parent_without_unique_key():

    db = sqlite3.connect(":memory:")

    try:
        db.execute(
            "PRAGMA foreign_keys=ON"
        )

        db.execute(
            "CREATE TABLE production_intervals "
            "(run_id INTEGER, start_utc TEXT)"
        )

        with pytest.raises(
            ValueError,
            match="UNIQUE/PK",
        ):
            initialize_ges_inverter_schema(db)

    finally:
        db.close()


def test_migration_does_not_implicitly_commit():

    db = create_demo_db()

    try:
        db.execute("BEGIN")

        initialize_ges_inverter_schema(db)

        assert db.in_transaction

        db.rollback()

        assert db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE name='ges_inverter_intervals'"
        ).fetchone() is None

    finally:
        db.close()

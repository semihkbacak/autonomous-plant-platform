
from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_FILE = Path(__file__).with_name(
    "ges_history_schema.sql"
)


def initialize_ges_inverter_schema(
    db: sqlite3.Connection,
) -> None:
    """
    Create only ges_* tables.

    Does not commit transactions.
    Does not change existing production rows.
    """

    # 1. Foreign key enforcement must already be on.
    if db.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0] != 1:
        raise ValueError(
            "PRAGMA foreign_keys=ON gerekli"
        )

    # 2. Verify existing plant interval parent.
    parent = db.execute(
        "PRAGMA table_info(production_intervals)"
    ).fetchall()

    parent_columns = {
        row[1]
        for row in parent
    }

    required = {
        "run_id",
        "start_utc",
    }

    if not required.issubset(parent_columns):
        raise ValueError(
            "production_intervals parent tablosu eksik"
        )

    # 3. Confirm parent has a matching unique key.
    pk_order = [
        row[1]
        for row in sorted(
            parent,
            key=lambda item: item[5],
        )
        if row[5]
    ]

    unique_parent_key = (
        pk_order == ["run_id", "start_utc"]
    )

    for index in db.execute(
        "PRAGMA index_list(production_intervals)"
    ):
        if not index[2]:
            continue

        index_name = index[1].replace(
            '"',
            '""',
        )

        indexed_columns = [
            row[2]
            for row in db.execute(
                f'PRAGMA index_info("{index_name}")'
            )
        ]

        if indexed_columns == [
            "run_id",
            "start_utc",
        ]:
            unique_parent_key = True
            break

    if not unique_parent_key:
        raise ValueError(
            "production_intervals(run_id,start_utc) "
            "UNIQUE/PK gerekli"
        )

    # 4. Apply additive schema without executescript.
    sql = SCHEMA_FILE.read_text(
        encoding="utf-8"
    )

    for statement in sql.split(";"):
        if statement.strip():
            db.execute(statement)


"""Atomic MPPT and P-Q Historian extension."""

from __future__ import annotations

import json
import sqlite3

from math import fsum, isclose, isfinite


def initialize_mppt_schema(
    db: sqlite3.Connection,
) -> None:
    """
    Call inside the SolarHistorian schema transaction.
    Does not commit.
    """

    db.execute("""
        CREATE TABLE IF NOT EXISTS ges_mppt_intervals (
            run_id INTEGER NOT NULL,
            start_utc TEXT NOT NULL,
            inverter_id TEXT NOT NULL,

            channel INTEGER NOT NULL
                CHECK(channel > 0),

            end_utc TEXT NOT NULL,

            vmp_v REAL NOT NULL
                CHECK(vmp_v >= 0),

            imp_a REAL NOT NULL
                CHECK(imp_a >= 0),

            voc_v REAL NOT NULL
                CHECK(voc_v >= 0),

            isc_a REAL NOT NULL
                CHECK(isc_a >= 0),

            dc_offered_kw REAL NOT NULL
                CHECK(dc_offered_kw >= 0),

            dc_accepted_kw REAL NOT NULL
                CHECK(dc_accepted_kw >= 0),

            dc_rejected_kw REAL NOT NULL
                CHECK(dc_rejected_kw >= 0),

            reasons_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,

            PRIMARY KEY (
                run_id,
                start_utc,
                inverter_id,
                channel
            ),

            FOREIGN KEY(run_id, start_utc)
                REFERENCES production_intervals(
                    run_id,
                    start_utc
                )
                ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_ges_mppt_run_inverter
        ON ges_mppt_intervals(
            run_id,
            inverter_id,
            start_utc
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS ges_pq_intervals (
            run_id INTEGER NOT NULL,
            start_utc TEXT NOT NULL,
            inverter_id TEXT NOT NULL,
            end_utc TEXT NOT NULL,

            requested_reactive_kvar REAL NOT NULL,

            applied_kva_limit REAL NOT NULL
                CHECK(applied_kva_limit > 0),

            active_limit_kw REAL NOT NULL
                CHECK(active_limit_kw >= 0),

            warnings_json TEXT NOT NULL,

            PRIMARY KEY (
                run_id,
                start_utc,
                inverter_id
            ),

            FOREIGN KEY(run_id, start_utc)
                REFERENCES production_intervals(
                    run_id,
                    start_utc
                )
                ON DELETE CASCADE
        )
    """)


def append_mppt_interval(
    db: sqlite3.Connection,
    run_id: int,
    record,
    *,
    require_mppt_reports: bool = False,
) -> None:
    """
    Append MPPT/P-Q rows in the parent transaction.

    Never commits independently.
    A failed validation or INSERT rolls back the run.
    """

    reports = tuple(
        getattr(record, "mppt_reports", ())
    )

    if not reports:
        if require_mppt_reports:
            raise ValueError(
                "Integrated GES interval missing MPPT reports"
            )
        return

    if not db.in_transaction:
        raise ValueError(
            "MPPT rows require parent transaction"
        )

    inverter_map = {
        result.inverter_id: result
        for result in record.inverter_results
    }

    if len(inverter_map) != len(record.inverter_results):
        raise ValueError(
            "Duplicate inverter in parent interval"
        )

    seen_inverters = set()

    for report in reports:

        iid = report.inverter_id

        if (
            iid not in inverter_map
            or iid in seen_inverters
        ):
            raise ValueError(
                "Unknown or duplicate MPPT inverter"
            )

        seen_inverters.add(iid)

        mppt = report.dc

        if not mppt.channels:
            raise ValueError(
                "Empty MPPT channels"
            )

        expected = inverter_map[iid]

        if not isclose(
            mppt.dc_offered_kw,
            expected.dc_offered_kw,
            rel_tol=0,
            abs_tol=1e-5,
        ):
            raise ValueError(
                "MPPT/inverter offered DC mismatch"
            )

        if (
            expected.status != "BLOCKED"
            and not isclose(
                mppt.dc_accepted_kw,
                expected.dc_accepted_kw,
                rel_tol=0,
                abs_tol=1e-5,
            )
        ):
            raise ValueError(
                "MPPT/inverter accepted DC mismatch"
            )

        channels_seen = set()

        for channel in mppt.channels:

            if channel.channel in channels_seen:
                raise ValueError(
                    "Duplicate channel in MPPT history"
                )

            channels_seen.add(
                channel.channel
            )

            numbers = (
                channel.voltage_v,
                channel.current_a,
                channel.open_circuit_v,
                channel.short_circuit_a,
                channel.offered_kw,
                channel.accepted_kw,
                channel.rejected_kw,
            )

            if any(
                not isfinite(value) or value < 0
                for value in numbers
            ):
                raise ValueError(
                    "Invalid MPPT electrical values"
                )

            if not isclose(
                channel.offered_kw,
                channel.accepted_kw + channel.rejected_kw,
                rel_tol=0,
                abs_tol=1e-5,
            ):
                raise ValueError(
                    "MPPT DC balance mismatch"
                )

            db.execute("""
                INSERT INTO ges_mppt_intervals (
                    run_id,
                    start_utc,
                    inverter_id,
                    channel,
                    end_utc,
                    vmp_v,
                    imp_a,
                    voc_v,
                    isc_a,
                    dc_offered_kw,
                    dc_accepted_kw,
                    dc_rejected_kw,
                    reasons_json,
                    warnings_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                run_id,
                record.start_utc.isoformat(),
                iid,
                channel.channel,
                record.end_utc.isoformat(),
                channel.voltage_v,
                channel.current_a,
                channel.open_circuit_v,
                channel.short_circuit_a,
                channel.offered_kw,
                channel.accepted_kw,
                channel.rejected_kw,
                json.dumps(channel.reasons),
                json.dumps(mppt.warnings),
            ))

        if not isclose(
            fsum(
                channel.offered_kw
                for channel in mppt.channels
            ),
            mppt.dc_offered_kw,
            rel_tol=0,
            abs_tol=1e-5,
        ):
            raise ValueError(
                "MPPT total offered mismatch"
            )

        if not isclose(
            fsum(
                channel.accepted_kw
                for channel in mppt.channels
            ),
            mppt.dc_accepted_kw,
            rel_tol=0,
            abs_tol=1e-5,
        ):
            raise ValueError(
                "MPPT total accepted mismatch"
            )

    # Legacy intervals may have no MPPT reports at all.
    # Once reports exist, they must cover every inverter.
    if seen_inverters != set(inverter_map):
        raise ValueError(
            "Missing MPPT report for inverter(s): "
            + ", ".join(
                sorted(set(inverter_map) - seen_inverters)
            )
        )

    # --------------------------------------------------------
    # P-Q SCREENING HISTORY
    # --------------------------------------------------------

    # Requested Q and capability-screening values only.
    # Not measured or physically delivered reactive power.

    pq_seen = set()

    for pq in tuple(
        getattr(record, "pq_reports", ())
    ):

        if (
            pq.inverter_id not in inverter_map
            or pq.inverter_id in pq_seen
        ):
            raise ValueError(
                "Unknown or duplicate P-Q inverter"
            )

        pq_seen.add(
            pq.inverter_id
        )

        pq_numbers = (
            pq.requested_reactive_kvar,
            pq.applied_kva_limit,
            pq.active_limit_kw,
        )

        if (
            any(
                not isfinite(value)
                for value in pq_numbers
            )
            or pq.applied_kva_limit <= 0
            or pq.active_limit_kw < 0
        ):
            raise ValueError(
                "Invalid P-Q screening numbers"
            )

        if (
            pq.active_limit_kw
            > inverter_map[
                pq.inverter_id
            ].ac_available_kw + 1e-5
        ):
            raise ValueError(
                "P-Q cap exceeds inverter available power"
            )

        db.execute("""
            INSERT INTO ges_pq_intervals (
                run_id,
                start_utc,
                inverter_id,
                end_utc,
                requested_reactive_kvar,
                applied_kva_limit,
                active_limit_kw,
                warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            record.start_utc.isoformat(),
            pq.inverter_id,
            record.end_utc.isoformat(),
            pq.requested_reactive_kvar,
            pq.applied_kva_limit,
            pq.active_limit_kw,
            json.dumps(pq.warnings),
        ))

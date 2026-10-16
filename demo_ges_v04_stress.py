
"""GES v0.4 integrated synthetic stress test."""

from __future__ import annotations

import argparse
import sqlite3

from dataclasses import replace
from pathlib import Path

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.pq_dispatch import PQCapability

from simulator.solar.solar_historian_audit import (
    audit_solar_run,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)


def run_stress(days: int, output: Path) -> None:

    if type(days) is not int or not (1 <= days <= 365):
        raise ValueError("days must be between 1 and 365")

    pipeline = build_integrated_demo_pipeline()
    simulator = SolarTimeSeriesSimulator(pipeline)

    pq_capabilities = {
        iid: PQCapability(
            nameplate_kva=10.0,
            rated_active_kw=10.0,
        )
        for iid in pipeline.inverter_ids
    }

    reactive_requests = {
        iid: 8.0
        for iid in pipeline.inverter_ids
    }

    print(
        f"Starting GES v0.4 integrated {days}-day test",
        flush=True,
    )

    intervals = make_stress_intervals(days)

    for index, interval in enumerate(intervals, start=1):

        simulator.step(
            replace(
                interval,
                pq_capabilities=pq_capabilities,
                reactive_requests_kvar=reactive_requests,
            )
        )

        if index % 96 == 0:
            print(
                f"Completed day {index // 96}",
                flush=True,
            )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_path = output / "historian.sqlite3"

    historian = SolarHistorian(db_path)

    run_id = historian.save_simulation(
        simulator,
        scenario=f"GES_V04_STRESS_{days}D",
        inverter_snapshot_payloads=(
            build_integrated_snapshots(pipeline)
        ),
    )

    audit = audit_solar_run(
        db_path,
        run_id,
    )

    with sqlite3.connect(db_path) as db:

        db.execute("PRAGMA foreign_keys = ON")

        mppt_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_mppt_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        pq_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_pq_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        fk_errors = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    expected = days * 96

    checks = {
        "historian_audit": audit.ok,
        "plant_interval_count": (
            audit.interval_count == expected
        ),
        "inverter_interval_count": (
            audit.inverter_record_count == expected * 2
        ),
        "mppt_interval_count": (
            mppt_count == expected * 4
        ),
        "pq_interval_count": (
            pq_count == expected * 2
        ),
        "foreign_keys": not fk_errors,
    }

    print("\n=== GES V0.4 RESULTS ===")

    print("Run ID:", run_id)
    print("Plant intervals:", audit.interval_count)
    print("Inverter intervals:", audit.inverter_record_count)
    print("MPPT intervals:", mppt_count)
    print("P-Q intervals:", pq_count)
    print("Energy kWh:", round(audit.total_energy_kwh, 4))
    print("Audit issues:", audit.issues)
    print("Checks:", checks)

    if not all(checks.values()):
        raise SystemExit(
            "GES V0.4 INTEGRATED STRESS AUDIT FAILED"
        )

    print(
        "\nGES V0.4 INTEGRATED STRESS AUDIT OK"
    )
    print("Database:", db_path)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--days",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/ges_v04_stress"),
    )

    args = parser.parse_args()

    run_stress(
        days=args.days,
        output=args.output,
    )


if __name__ == "__main__":
    main()

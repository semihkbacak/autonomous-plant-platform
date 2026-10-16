
"""Long-run integrated GES v0.4 synthetic stress test."""
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

from simulator.solar.pq_dispatch import (
    PQCapability,
)

from simulator.solar.solar_historian_audit import (
    audit_solar_run,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)


def run(days: int, output: Path):

    if type(days) is not int or not (1 <= days <= 365):
        raise ValueError(
            "days must be in 1..365"
        )

    pipeline = build_integrated_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    pq = {
        iid: PQCapability(10, 10)
        for iid in pipeline.inverter_ids
    }

    requests = {
        iid: 8.0
        for iid in pipeline.inverter_ids
    }

    for index, interval in enumerate(
        make_stress_intervals(days),
        start=1,
    ):

        simulator.step(
            replace(
                interval,
                pq_capabilities=pq,
                reactive_requests_kvar=requests,
            )
        )

        if index % 96 == 0:
            print(
                f"Integrated v0.4 completed day {index // 96}",
                flush=True,
            )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    file = output / "historian.sqlite3"

    historian = SolarHistorian(file)

    run_id = historian.save_simulation(
        simulator,
        scenario=f"GES_V04_STRESS_{days}D_SYNTHETIC",
        inverter_snapshot_payloads=(
            build_integrated_snapshots(pipeline)
        ),
    )

    audit = audit_solar_run(
        file,
        run_id,
    )

    with sqlite3.connect(file) as db:

        mppt_rows = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_mppt_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        pq_rows = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_pq_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        fk_issues = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    expected_intervals = days * 96

    valid = (
        audit.ok
        and audit.interval_count == expected_intervals
        and mppt_rows == expected_intervals * 4
        and pq_rows == expected_intervals * 2
        and not fk_issues
    )

    print({
        "run_id": run_id,
        "historian_audit_ok": audit.ok,
        "plant_intervals": audit.interval_count,
        "inverter_intervals": audit.inverter_record_count,
        "mppt_intervals": mppt_rows,
        "pq_screen_intervals": pq_rows,
        "energy_kwh": audit.total_energy_kwh,
        "audit_issues": audit.issues,
        "foreign_key_issues": fk_issues,
    })

    if not valid:
        raise SystemExit(
            "GES V0.4 STRESS AUDIT FAILED"
        )

    print(
        "GES V0.4 INTEGRATED STRESS AUDIT OK",
        file,
    )


if __name__ == "__main__":

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

    run(
        args.days,
        args.output,
    )

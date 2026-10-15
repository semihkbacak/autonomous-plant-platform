"""HES v0.3 to v1.0 simulator-only release acceptance."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from simulator.hydro_history import HydroHistorian
from simulator.hydro_suite import (
    CASES,
    annual_steady_state,
    run_dynamic_case,
)


def run_scenarios(
    output: Path,
    *,
    seconds: int = 120,
    sample_every: int = 5,
) -> dict:

    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "hydro_history.sqlite3"

    if db_path.exists():
        raise FileExistsError(
            "Refusing to overwrite/append existing historian: "
            + str(db_path)
        )

    history = HydroHistorian(db_path)
    results = []

    for name in CASES:
        snapshots = run_dynamic_case(
            name,
            seconds=seconds,
            sample_every=sample_every,
        )

        run_id = history.save_run(
            name, snapshots
        )

        stats = history.summary(run_id)

        results.append({
            "case": name,
            "run_id": run_id,
            "duration_s": stats["duration_s"],
            "energy_mwh": stats["energy_mwh"],
            "raised_alarms": stats["alarm_raises"],
        })

        print(
            f"[{len(results)}/{len(CASES)}] "
            f"{name}: {stats['energy_mwh']:.6f} MWh"
        )

    audit = history.audit(set(CASES))

    manifest = {
        "scope": "SYNTHETIC_DYNAMIC_1S_SAMPLED",
        "cases": results,
        "sample_every_s": sample_every,
        "audit": audit,
    }

    (output / "hes_manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return manifest


def verify_protective_scenarios(
    db_path: Path,
) -> dict:

    h = HydroHistorian.for_reading(db_path)

    by_name = {
        r["scenario"]: r["id"]
        for r in h.runs()
    }

    checks = {}

    if not set(CASES) <= set(by_name):
        return {
            "passed": False,
            "checks": {},
            "issues": ["MISSING_CASES"],
        }

    samples = {
        name: h.samples(by_name[name])
        for name in CASES
    }

    alarms = {
        name: h.alarms(by_name[name])
        for name in CASES
    }

    energies = {
        name: h.summary(by_name[name])["energy_mwh"]
        for name in CASES
    }

    def raised(name, code):
        return any(
            a["code"] == code
            and a["transition"] == "RAISED"
            for a in alarms[name]
        )

    checks["BASELINE_POSITIVE_ENERGY"] = (
        energies["BASELINE"] > 0
    )

    checks["DUAL_GT_SINGLE"] = (
        energies["DUAL_UNIT"]
        > energies["BASELINE"]
    )

    checks["SETPOINT_REDUCES_ENERGY"] = (
        0 < energies["POWER_STEP"]
        < energies["BASELINE"]
    )

    checks["GRID_LOSS_PROTECTS_OUTPUT"] = (
        raised("GRID_LOSS", "GRID_LOSS")
        and samples["GRID_LOSS"][-1]["power_mw"] == 0
        and samples["GRID_LOSS"][-1]["emergency_stop"] == 1
    )

    checks["GRID_RECOVERY_ACKNOWLEDGED"] = (
        raised("GRID_RECOVERY", "GRID_LOSS")
        and any(
            a["code"] == "GRID_LOSS"
            and a["transition"] == "CLEARED"
            for a in alarms["GRID_RECOVERY"]
        )
        and samples["GRID_RECOVERY"][-1]["grid_available"] == 1
        and samples["GRID_RECOVERY"][-1]["emergency_stop"] == 0
    )

    for name, code in (
        ("UNIT_FAULT", "UNIT_FAULT"),
        ("HIGH_TEMPERATURE", "HIGH_BEARING_TEMPERATURE"),
        ("HIGH_VIBRATION", "HIGH_VIBRATION"),
    ):
        checks[name + "_TRIP"] = (
            raised(name, code)
            and samples[name][-1]["power_mw"] == 0
            and samples[name][-1]["emergency_stop"] == 1
        )

    for name in (
        "LOW_HEADPOND",
        "EMERGENCY_STOP",
        "MAINTENANCE_LOCK",
    ):
        checks[name + "_STOPS"] = (
            samples[name][-1]["power_mw"] == 0
            and samples[name][-1]["emergency_stop"] == 1
        )

    checks["LOW_HEAD_REDUCES_ENERGY"] = (
        energies["LOW_NET_HEAD"]
        < energies["BASELINE"]
    )

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "issues": [
            key for key, ok in checks.items()
            if not ok
        ],
    }


def acceptance(
    db_path: Path,
    *,
    annual_days: int = 0,
    regression: bool = False,
) -> dict:

    history = HydroHistorian.for_reading(db_path)

    audit = history.audit(set(CASES))
    protective = verify_protective_scenarios(db_path)

    report = {
        "release": "HES_V1.0_SIMULATION_CANDIDATE",

        "v0.3_historian": audit,

        "v0.4_dashboard_api": (
            "ROUTES_AVAILABLE_WHEN_INCLUDED_IN_APP"
        ),

        "v0.5_analytics": (
            "RECORDED_UNIT_GOVERNOR_ENERGY_ALARM_METRICS"
        ),

        "v0.6_scenarios": {
            "count": len(CASES),
            "names": list(CASES),
        },

        "v0.7_alarm_study": (
            "SAMPLED_RAISED_CLEARED_TRANSITIONS_ONLY"
        ),

        "v0.8_fault_integrity": protective,

        "v0.9_annual": {
            "status": "NOT_RUN",
        },

        "regression": {
            "status": "NOT_RUN",
        },

        "oem_hydraulic_calibration": False,
        "real_site_validation": False,
        "real_ot_connection": False,
    }

    if annual_days:
        report["v0.9_annual"] = (
            annual_steady_state(
                days=annual_days
            ).report()
        )

    if regression:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--assert=plain",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        report["regression"] = {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "tail": (
                completed.stdout + completed.stderr
            ).splitlines()[-12:],
        }

    passed = (
        audit["passed"]
        and protective["passed"]
        and report["v0.9_annual"].get("days") == 365
        and report["regression"].get("passed") is True
    )

    report["software_acceptance_passed"] = bool(passed)

    report["overall_status"] = (
        "HES_SIMULATION_SOFTWARE_ACCEPTED_NOT_FIELD_VALIDATED"
        if passed
        else "HES_CANDIDATE_INCOMPLETE"
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="New output directory for 12 cases",
    )

    parser.add_argument(
        "--existing-db",
        type=Path,
        help="Audit an existing HES database",
    )

    parser.add_argument(
        "--seconds",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--sample-every",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--annual-days",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--regression",
        action="store_true",
    )

    args = parser.parse_args()

    if (
        (args.output is None)
        == (args.existing_db is None)
    ):
        parser.error(
            "Choose exactly one of --output or --existing-db"
        )

    if args.output:
        run_scenarios(
            args.output,
            seconds=args.seconds,
            sample_every=args.sample_every,
        )

        db = args.output / "hydro_history.sqlite3"
        output = args.output

    else:
        db = args.existing_db
        output = db.parent

    if not db.is_file():
        parser.error(
            f"Database not found: {db}"
        )

    report = acceptance(
        db,
        annual_days=args.annual_days,
        regression=args.regression,
    )

    outfile = output / "hes_v10_acceptance.json"

    outfile.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("Saved:", outfile)

    return (
        0
        if report["software_acceptance_passed"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
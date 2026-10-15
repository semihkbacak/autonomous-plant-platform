
"""GES v1.0 simulation release acceptance (NO live OT or field claims).

Examples:
  python ges_v10_release.py --matrix /path/to/ges_v05_p03_final --regression
  python ges_v10_release.py --matrix /path/to/ges_v05_p03_final --observations actual.csv
  python ges_v10_release.py --annual-days 365 --annual-case BASELINE_PQ8
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from simulator.solar.ges_v10_quality import (
    audit_scenario_matrix,
    compare_power_csv,
)


def annual_smoke(days: int, case: str) -> dict:
    from demo_ges_v05_scenarios import (
        CASE_BY_NAME,
        run_case,
    )
    from simulator.solar.solar_stress import (
        make_stress_intervals,
    )

    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("days must be in 1..365")
    if case not in CASE_BY_NAME:
        raise ValueError("Unknown scenario")

    # No database: avoids large SQLite files and NTFS overhead.
    result = run_case(
        CASE_BY_NAME[case],
        make_stress_intervals(days),
        None,
    )
    assert result["intervals"] == days * 96

    return {
        "days": days,
        "scenario": case,
        "intervals": result["intervals"],
        "energy_kwh": result["energy_kwh"],
        "scope": "SYNTHETIC_NOT_FIELD_VALIDATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        help="Directory with 54-case scenario DB and manifest",
    )
    parser.add_argument(
        "--research-zip",
        type=Path,
        default=Path("ges_oem_research.zip"),
    )
    parser.add_argument(
        "--observations",
        type=Path,
        help="Optional measured vs predicted 15-minute CSV",
    )
    parser.add_argument(
        "--regression",
        action="store_true",
        help="Run pytest as acceptance evidence",
    )
    parser.add_argument(
        "--annual-days",
        type=int,
        default=0,
        help="Run deterministic 1..365 day check",
    )
    parser.add_argument(
        "--annual-case",
        default="BASELINE_PQ8",
    )
    args = parser.parse_args()

    if args.matrix is None and not args.annual_days:
        parser.error(
            "Specify --matrix and/or --annual-days"
        )

    report = {
        "release": "GES_SIMULATION_V1.0_CANDIDATE",
        "claims": {
            "simulator_only": True,
            "oem_calibrated": False,
            "field_validated": False,
            "real_plant_control_enabled": False,
        },
    }
    passed = True

    if args.matrix is not None:
        audit = audit_scenario_matrix(args.matrix)
        report["matrix"] = audit.as_dict()
        passed &= audit.passed

    if args.research_zip.is_file():
        from simulator.solar.oem_research_bridge import (
            load_researched_oem_catalog,
        )
        from simulator.solar.oem_model_readiness import (
            assess_oem_readiness,
        )

        catalog = load_researched_oem_catalog(
            args.research_zip
        )
        panels = [
            c for c in catalog.components.values()
            if c.component_type == "panel"
        ]
        inverters = [
            c for c in catalog.components.values()
            if c.component_type == "inverter"
        ]

        report["oem_research"] = {
            "catalog_sha256": catalog.catalog_sha256,
            "accepted_as_declared": catalog.accepted_count,
            "quarantined": catalog.quarantined_count,
            "ready_pairs": [
                (p.component_id, i.component_id)
                for p in panels
                for i in inverters
                if assess_oem_readiness(
                    p, i
                ).real_physics_ready
            ],
            "warning": (
                "Metadata is not independent "
                "manufacturer verification"
            ),
        }
    else:
        report["oem_research"] = {
            "status": "RESEARCH_ZIP_NOT_FOUND"
        }

    if args.observations:
        report["comparison"] = compare_power_csv(
            args.observations
        )

    if args.annual_days:
        report["annual"] = annual_smoke(
            args.annual_days,
            args.annual_case,
        )

    if args.regression:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--assert=plain",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        report["regression"] = {
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "summary": (
                completed.stdout + completed.stderr
            ).splitlines()[-12:],
        }
        passed &= completed.returncode == 0

    report["simulation_acceptance_passed"] = bool(
        passed
    )
    report["overall_claim"] = (
        "SIMULATION_QUALITY_GATE_PASSED_NOT_OEM_OR_FIELD_VALIDATED"
        if passed
        else "SIMULATION_QUALITY_GATE_FAILED"
    )

    if args.matrix:
        target = (
            args.matrix / "ges_v10_acceptance.json"
        )
        target.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print("Acceptance JSON:", target)

    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

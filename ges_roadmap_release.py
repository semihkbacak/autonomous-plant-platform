"""GES 0.6 -> 1.0 staged software acceptance.

Simulator only. No OEM calibration or field control claims.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from simulator.solar.ges_v09_validation import (
    run_long_horizon,
    compare_external_measurements,
)
from simulator.solar.ges_v10_quality import (
    audit_scenario_matrix,
)
from simulator.solar.oem_research_bridge import (
    load_researched_oem_catalog,
)
from simulator.solar.oem_model_readiness import (
    assess_oem_readiness,
)


def examine_oem_research(path: Path) -> dict:

    if not path.is_file():
        return {
            "status": "MISSING_RESEARCH",
            "model_ready": False,
        }

    catalog = load_researched_oem_catalog(path)

    panels = [
        c for c in catalog.components.values()
        if c.component_type == "panel"
    ]

    inverters = [
        c for c in catalog.components.values()
        if c.component_type == "inverter"
    ]

    pairs = [
        (p.component_id, i.component_id)
        for p in panels
        for i in inverters
        if assess_oem_readiness(
            p, i
        ).real_physics_ready
    ]

    return {
        "status": "CATALOG_IMPORTED_NOT_INDEPENDENTLY_VERIFIED",
        "accepted_as_declared": catalog.accepted_count,
        "quarantined": catalog.quarantined_count,
        "catalog_sha256": catalog.catalog_sha256,
        "model_ready_pairs": pairs,
        "model_ready": bool(pairs),
    }


def check_release(
    matrix: Path,
    research: Path,
    *,
    days: int = 0,
    regression: bool = False,
    observations: Path | None = None,
) -> dict:

    audit = audit_scenario_matrix(matrix)

    research_report = examine_oem_research(
        research
    )

    result = {
        "release": "GES_V1.0_SIMULATION_CANDIDATE",

        "v0.6_oem": research_report,

        "v0.7_physics": {
            "integrated_inverter_curves": "OPT_IN",
            "partial_shading_string": (
                "RESEARCH_BYPASS_APPROXIMATION_ONLY"
            ),
            "full_parallel_shading_validated": False,
        },

        "v0.8_safety": {
            "telemetry_supervisor": (
                "SIMULATOR_ONLY_OPT_IN"
            ),
            "real_ot_safety_validated": False,
        },

        "v0.9_longrun": {
            "status": "NOT_RUN"
        },

        "v1.0_matrix": audit.as_dict(),

        "regression": {
            "status": "NOT_RUN"
        },

        "field": {
            "status": "NOT_VALIDATED"
        },
    }

    if days:
        result["v0.9_longrun"] = (
            run_long_horizon(days).report()
        )

    if observations:
        result["field"]["comparison"] = (
            compare_external_measurements(
                observations
            )
        )

    if regression:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--assert=plain",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        result["regression"] = {
            "passed": proc.returncode == 0,
            "exit_code": proc.returncode,
            "tail": (
                proc.stdout + proc.stderr
            ).splitlines()[-8:],
        }

    complete = bool(
        audit.passed
        and days == 365
        and result["v0.9_longrun"].get("valid") is True
        and result["regression"].get("passed") is True
    )

    result["software_release_gate_passed"] = complete
    result["oem_calibration_gate_passed"] = False
    result["field_validation_gate_passed"] = False

    result["overall_status"] = (
        "SIMULATION_SOFTWARE_ACCEPTED_OEM_FIELD_NOT_VALIDATED"
        if complete
        else "CANDIDATE_INCOMPLETE"
    )

    return result


def main() -> int:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--matrix",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--research",
        type=Path,
        default=Path("ges_oem_research.zip"),
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

    parser.add_argument(
        "--observations",
        type=Path,
    )

    parser.add_argument(
        "--report",
        type=Path,
    )

    args = parser.parse_args()

    report = check_release(
        args.matrix,
        args.research,
        days=args.annual_days,
        regression=args.regression,
        observations=args.observations,
    )

    if args.report:
        args.report.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        args.report.write_text(
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

    return (
        0
        if report["software_release_gate_passed"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
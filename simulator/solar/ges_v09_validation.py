"""v0.9: long-horizon synthetic study and benchmark metrics.

Shared pvlib internals are not independent physical validation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from pathlib import Path

from simulator.solar.ges_v10_quality import (
    compare_power_csv,
)


@dataclass(frozen=True)
class LongRunResult:
    scenario: str
    days: int
    intervals: int

    ac_energy_kwh: float
    ac_peak_kw: float

    dc_offered_kwh: float
    dc_accepted_kwh: float
    dc_rejected_kwh: float

    curtailment_kwh: float
    alarm_transitions: int
    valid: bool

    source_kind: str = (
        "SYNTHETIC_STRESS_NOT_FIELD_DATA"
    )

    def report(self) -> dict:
        return asdict(self)


def run_long_horizon(
    days: int = 365,
    *,
    scenario: str = "BASELINE_PQ8",
) -> LongRunResult:

    from demo_ges_v05_scenarios import (
        CASE_BY_NAME,
        run_case,
    )

    from simulator.solar.solar_stress import (
        make_stress_intervals,
    )

    if (
        type(days) is not int
        or not 1 <= days <= 365
    ):
        raise ValueError(
            "Days must be an integer in 1..365"
        )

    if scenario not in CASE_BY_NAME:
        raise ValueError(
            "Unknown GES scenario"
        )

    intervals = make_stress_intervals(days)

    result = run_case(
        CASE_BY_NAME[scenario],
        intervals,
        None,
    )

    energy = result["energy_kwh"]
    offered = result["dc_offered_kwh"]
    accepted = result["dc_accepted_kwh"]
    rejected = result["dc_rejected_kwh"]

    if any(
        not isfinite(v) or v < 0
        for v in (
            energy,
            offered,
            accepted,
            rejected,
        )
    ):
        raise ValueError(
            "Invalid energy in annual study"
        )

    valid = (
        result["intervals"] == 96 * days
        and energy >= 0
        and accepted <= offered + 2e-5
        and abs(
            offered - accepted - rejected
        ) < 2e-4
    )

    if not valid:
        raise ValueError(
            "Long horizon physical accounting invalid"
        )

    return LongRunResult(
        scenario=scenario,
        days=days,
        intervals=result["intervals"],
        ac_energy_kwh=energy,
        ac_peak_kw=result["peak_ac_kw"],
        dc_offered_kwh=offered,
        dc_accepted_kwh=accepted,
        dc_rejected_kwh=rejected,
        curtailment_kwh=result["ac_curtailment_kwh"],
        alarm_transitions=result["alarm_transitions"],
        valid=True,
    )


def compare_external_measurements(
    path: str | Path,
) -> dict:
    """No interpolation, invented timestamps or fabricated measurements."""

    report = compare_power_csv(path)

    report["validation_scope"] = (
        "SOURCE_AND_SITE_UNVERIFIED"
    )

    report["field_accepted"] = False

    return report
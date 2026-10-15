"""Deterministic, read-only quality and synchronized energy calculations.

This is a simulator/research layer. It cannot actuate physical equipment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from collections import Counter
from typing import Any

PLANTS = ("HES", "GES", "RES")


def finite_nonnegative(value: Any) -> bool:
    return (not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def inspect_telemetry(plant: str, state: dict[str, Any] | None) -> dict[str, Any]:
    """Validate already-produced synthetic values; do NOT equate to sensor QA."""
    if plant not in PLANTS:
        raise ValueError("Unknown plant")
    issues: list[str] = []
    if state is None:
        return {"plant": plant, "quality": "UNAVAILABLE", "issues": ["SOURCE_UNAVAILABLE"],
                "freshness": "UNVERIFIED", "source": "SIMULATION_ONLY"}
    power = state.get("power_kw")
    if not finite_nonnegative(power):
        issues.append("INVALID_POWER")
    energy = state.get("energy_kwh")
    if energy is not None and not finite_nonnegative(energy):
        issues.append("INVALID_ENERGY")
    if state.get("error"):
        issues.append("MODEL_ERROR_LATCHED")
    units = state.get("units", [])
    if not isinstance(units, list):
        issues.append("INVALID_UNIT_COLLECTION")
        units = []
    identifiers = []
    unit_kw = []
    for item in units:
        if not isinstance(item, dict):
            issues.append("INVALID_UNIT_ROW")
            continue
        identity = item.get("id")
        if not isinstance(identity, str) or not identity:
            issues.append("INVALID_UNIT_ID")
        else:
            identifiers.append(identity)
        kw = item.get("kw")
        if not finite_nonnegative(kw):
            issues.append("INVALID_UNIT_POWER")
        else:
            unit_kw.append(float(kw))
    if len(identifiers) != len(set(identifiers)):
        issues.append("DUPLICATE_UNIT_ID")
    # Only reconcile power when a complete unit record set is available.
    if units and len(unit_kw) == len(units) and finite_nonnegative(power):
        tolerance = max(0.02, 0.001 * max(1, power))
        if abs(math.fsum(unit_kw) - float(power)) > tolerance:
            issues.append("UNIT_POWER_MISMATCH")
    return {"plant": plant, "quality": "INVALID" if issues else "VALID_SYNTHETIC",
            "issues": sorted(set(issues)), "freshness": "UNVERIFIED",
            "source": "SIMULATION_ONLY"}


def _dt(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO8601 UTC string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO8601 time") from exc
    if result.tzinfo is None or result.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("All interval timestamps must explicitly be UTC")
    return result.astimezone(timezone.utc)


def validate_synchronized_portfolio(records: list[dict], *, max_intervals: int = 1000) -> dict:
    """Each row: plant,start_utc,end_utc,mean_power_kw,source_kind.

    Strict identical closed-open windows across plants. Never mix historic runs
    whose clocks differ. Returns energy only from explicitly aligned inputs.
    """
    if not isinstance(records, list) or len(records) < 3 or len(records) > 3 * max_intervals:
        raise ValueError("Invalid portfolio record count")
    by_plant: dict[str, dict[tuple[datetime, datetime], float]] = {p: {} for p in PLANTS}
    kind_set: set[str] = set()
    for r in records:
        if not isinstance(r, dict):
            raise ValueError("Portfolio record must be an object")
        plant = r.get("plant")
        if plant not in by_plant:
            raise ValueError("Unknown plant")
        start, end = _dt(r.get("start_utc")), _dt(r.get("end_utc"))
        seconds = (end - start).total_seconds()
        if not (0 < seconds <= 3600):
            raise ValueError("Invalid interval duration")
        power = r.get("mean_power_kw")
        if not finite_nonnegative(power):
            raise ValueError("Invalid mean power")
        kind = r.get("source_kind")
        if kind != "SYNTHETIC_ALIGNED":
            raise ValueError("Only explicit synchronized synthetic series accepted")
        kind_set.add(kind)
        key = (start, end)
        if key in by_plant[plant]:
            raise ValueError("Duplicate interval")
        by_plant[plant][key] = float(power)
    windows = [set(by_plant[p]) for p in PLANTS]
    if not windows[0] or any(w != windows[0] for w in windows[1:]):
        raise ValueError("Cross-plant timestamps differ; do not aggregate")
    ordered = sorted(windows[0])
    for current, nxt in zip(ordered, ordered[1:]):
        if current[1] != nxt[0]:
            raise ValueError("Gap or overlap in synchronized clock")
    per_plant = {
        p: math.fsum(by_plant[p][key] * (key[1] - key[0]).total_seconds() / 3600
                     for key in ordered)
        for p in PLANTS
    }
    return {
        "scope": "SYNTHETIC_ALIGNED_INTERVALS_ONLY",
        "field_validation": False,
        "independently_recorded_history_can_be_summed": False,
        "interval_count": len(ordered),
        "start_utc": ordered[0][0].isoformat(),
        "end_utc": ordered[-1][1].isoformat(),
        "energy_kwh_by_plant": per_plant,
        "total_energy_kwh": math.fsum(per_plant.values()),
        "total_mean_power_kw": math.fsum(per_plant.values()) / (
            (ordered[-1][1] - ordered[0][0]).total_seconds() / 3600),
    }


def generate_fault_matrix() -> list[dict]:
    """Run software-quality faults, never claim to simulate physical faults."""
    base = {"power_kw": 10.0, "energy_kwh": 2.5,
            "units": [{"id": "A", "kw": 4.0}, {"id": "B", "kw": 6.0}]}
    cases = [
        ("NOMINAL", base, "VALID_SYNTHETIC"),
        ("MISSING_SOURCE", None, "UNAVAILABLE"),
        ("NEGATIVE_POWER", {**base, "power_kw": -1.0}, "INVALID"),
        ("NAN_POWER", {**base, "power_kw": float('nan')}, "INVALID"),
        ("INF_POWER", {**base, "power_kw": float('inf')}, "INVALID"),
        ("BOOLEAN_POWER", {**base, "power_kw": True}, "INVALID"),
        ("NEGATIVE_ENERGY", {**base, "energy_kwh": -1.0}, "INVALID"),
        ("UNIT_MISMATCH", {**base, "power_kw": 50.0}, "INVALID"),
        ("DUPLICATE_IDS", {**base, "units": [{"id": "A", "kw": 4.0}, {"id": "A", "kw": 6.0}]}, "INVALID"),
        ("MISSING_UNIT_ID", {**base, "units": [{"kw": 4.0}, {"id": "B", "kw": 6.0}]}, "INVALID"),
        ("INVALID_UNIT_KW", {**base, "units": [{"id": "A", "kw": -1.0}, {"id": "B", "kw": 6.0}]}, "INVALID"),
        ("MODEL_FAILURE", {**base, "error": "SyntheticFailure"}, "INVALID"),
        ("MALFORMED_UNITS", {**base, "units": "UNIT_1"}, "INVALID"),
        ("INFINITE_UNIT", {**base, "units": [{"id": "A", "kw": float('inf')}, {"id": "B", "kw": 6.0}]}, "INVALID"),
    ]
    return [{"case": name, "passed": inspect_telemetry("GES", state)["quality"] == expected,
             "expected": expected, "actual": inspect_telemetry("GES", state)["quality"]}
            for name, state, expected in cases]

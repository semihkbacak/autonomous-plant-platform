"""30 deterministic telemetry/interface fault studies, not physical fault simulations.

These assert that questionable or stale user-supplied data cannot be promoted
into trustworthy field measurements. No production settings are inferred.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.site_shadow import FIELDS, ShadowStore

NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
BASE = {
    "HES": ("UNIT_1", "active_power_kw", "kW", "3000"),
    "GES": ("INV_1", "active_power_kw", "kW", "200"),
    "RES": ("WT_1", "active_power_kw", "kW", "1400"),
}
FAULTS = (
    "NORMAL", "NONFINITE", "NEGATIVE", "WRONG_UNIT", "NAIVE_TIME",
    "FUTURE_TIME", "BAD_QUALITY", "UNCERTAIN_QUALITY", "STALE", "DUPLICATE",
)


def simulate_case(plant: str, fault: str) -> dict:
    if plant not in BASE or fault not in FAULTS:
        raise ValueError("Unknown case")
    equipment, metric, unit, value = BASE[plant]
    row = {
        "site_id": "DEMO_ONLY", "plant": plant,
        "equipment_id": equipment, "metric": metric, "unit": unit,
        "timestamp_utc": (NOW - timedelta(seconds=30)).isoformat(),
        "value": value, "quality": "GOOD", "source_ref": "synthetic_fixtures",
    }
    if fault == "NONFINITE": row["value"] = "nan"
    if fault == "NEGATIVE": row["value"] = "-5"
    if fault == "WRONG_UNIT": row["unit"] = "MW"
    if fault == "NAIVE_TIME": row["timestamp_utc"] = NOW.replace(tzinfo=None).isoformat()
    if fault == "FUTURE_TIME": row["timestamp_utc"] = (NOW + timedelta(hours=1)).isoformat()
    if fault == "BAD_QUALITY": row["quality"] = "BAD"
    if fault == "UNCERTAIN_QUALITY": row["quality"] = "UNCERTAIN"
    if fault == "STALE": row["timestamp_utc"] = (NOW - timedelta(days=1)).isoformat()
    with TemporaryDirectory(prefix="plant_fault_lab_") as tmp:
        path = Path(tmp) / "offline.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader(); writer.writerow(row)
            if fault == "DUPLICATE": writer.writerow(row)
        store = ShadowStore(Path(tmp) / "shadow.sqlite3")
        try:
            store.import_csv(path, now=NOW)
            status = store.latest(now=NOW)
            accepted = status["all_usable_for_study"]
            verdict = "ACCEPTED_FOR_OFFLINE_STUDY" if accepted else "QUARANTINED_FOR_STUDY"
        except ValueError:
            verdict = "REJECTED"
    expected = {
        "NORMAL": "ACCEPTED_FOR_OFFLINE_STUDY",
        "BAD_QUALITY": "QUARANTINED_FOR_STUDY",
        "UNCERTAIN_QUALITY": "QUARANTINED_FOR_STUDY",
        "STALE": "QUARANTINED_FOR_STUDY",
    }.get(fault, "REJECTED")
    return {"plant": plant, "fault": fault, "verdict": verdict,
            "expected": expected, "passed": verdict == expected,
            "scope": "OFFLINE_TELEMETRY_QA_NOT_PHYSICAL_FAULT_MODEL"}


def fault_matrix() -> dict:
    cases = [simulate_case(plant, fault) for plant in BASE for fault in FAULTS]
    return {"cases": cases, "case_count": len(cases),
            "passed": all(r["passed"] for r in cases),
            "physical_fault_coverage": False,
            "oem_field_validation": False}

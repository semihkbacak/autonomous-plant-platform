
"""GES v1.0 simulation release checks and optional measured-data comparison.

Read-only on input SQLite and CSV. This does not validate a physical site.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import fsum, isclose, sqrt
from pathlib import Path


@dataclass(frozen=True)
class Acceptance:
    passed: bool
    checks: dict[str, bool]
    issues: tuple[str, ...]
    details: dict

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "issues": list(self.issues),
            "details": self.details,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_scenario_matrix(
    output: str | Path,
    *,
    require_full: bool = True,
) -> Acceptance:
    """Check a newly produced 1-day scenario matrix.

    BASELINE_NO_Q is exempt from P-Q report generation.
    This is a simulation quality gate, not field validation.
    """
    from demo_ges_v05_scenarios import CASE_BY_NAME

    output = Path(output)
    issues: list[str] = []
    checks: dict[str, bool] = {}

    def check(name: str, valid: bool) -> None:
        checks[name] = bool(valid)
        if not valid:
            issues.append(name)

    manifest_path = output / "scenario_manifest.json"
    db_path = output / "historian.sqlite3"
    csv_path = output / "scenario_results.csv"

    if not all(
        p.is_file()
        for p in (manifest_path, db_path, csv_path)
    ):
        return Acceptance(
            False, {}, ("MISSING_ARTIFACTS",), {}
        )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    with csv_path.open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    results = manifest.get("results", [])
    names = [r.get("name", "") for r in results]
    required = set(CASE_BY_NAME)

    check(
        "SYNTHETIC_PROVENANCE",
        manifest.get("data_kind") == "SYNTHETIC_SIMULATION_ONLY",
    )
    check(
        "ONE_DAY_PER_SCENARIO",
        manifest.get("days_per_case") == 1,
    )
    check(
        "UNIQUE_CASES",
        len(names) == len(set(names)),
    )
    check(
        "EXPECTED_CASES",
        set(names) == required
        if require_full
        else bool(names) and set(names) <= required,
    )
    check(
        "CSV_MANIFEST_MATCH",
        len(rows) == len(results) and all(
            r.get("name") == m.get("name")
            and isclose(
                float(r["energy_kwh"]),
                float(m["energy_kwh"]),
                abs_tol=1e-6,
            )
            for r, m in zip(rows, results)
        ),
    )

    # SQLite opened read-only.
    with sqlite3.connect(
        db_path.resolve().as_uri() + "?mode=ro",
        uri=True,
    ) as db:

        check(
            "SQLITE_INTEGRITY",
            db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0] == "ok",
        )
        check(
            "SQLITE_FOREIGN_KEYS",
            not db.execute(
                "PRAGMA foreign_key_check"
            ).fetchall(),
        )

        run_rows = db.execute(
            "SELECT id, scenario, interval_count, total_energy_kwh "
            "FROM simulation_runs ORDER BY id"
        ).fetchall()

        check(
            "RUN_IDENTITIES",
            Counter(r[1] for r in run_rows)
            == Counter(names),
        )
        check(
            "RUN_COUNT",
            len(run_rows) == len(results),
        )

        manifest_energies = {
            r["name"]: r["energy_kwh"]
            for r in results
        }
        check(
            "RUN_MANIFEST_ENERGY",
            all(
                scenario in manifest_energies
                and isclose(
                    float(energy),
                    float(manifest_energies[scenario]),
                    rel_tol=0,
                    abs_tol=1e-3,
                )
                for _, scenario, _, energy in run_rows
            ),
        )
        check(
            "EXPECTED_INTERVAL_COUNTS",
            all(r[2] == 96 for r in run_rows),
        )

        tables = (
            "production_intervals",
            "ges_inverter_intervals",
            "ges_mppt_intervals",
            "ges_pq_intervals",
        )

        counts = {
            name: db.execute(
                "SELECT COUNT(*) FROM " + name
            ).fetchone()[0]
            for name in tables
        }

        n = len(run_rows)

        check(
            "PLANT_ROWS",
            counts["production_intervals"] == n * 96,
        )
        check(
            "INVERTER_ROWS",
            counts["ges_inverter_intervals"] == n * 96 * 2,
        )
        check(
            "MPPT_ROWS",
            counts["ges_mppt_intervals"] == n * 96 * 4,
        )
        check(
            "PQ_ROWS",
            counts["ges_pq_intervals"]
            == (n - ("BASELINE_NO_Q" in names)) * 96 * 2,
        )

        energy_correct = True
        timeline_correct = True

        for run_id, scenario, _, energy in run_rows:
            intervals = db.execute(
                "SELECT start_utc, end_utc, dispatched_power_kw, "
                "interval_energy_kwh, cumulative_energy_kwh "
                "FROM production_intervals "
                "WHERE run_id=? ORDER BY start_utc",
                (run_id,),
            ).fetchall()

            if len(intervals) != 96:
                timeline_correct = energy_correct = False
                continue

            cumulative = 0.0
            prev_end = None

            for (
                start, end, power,
                energy_interval, cumulative_db
            ) in intervals:
                try:
                    a = datetime.fromisoformat(start)
                    b = datetime.fromisoformat(end)
                    time_ok = (
                        a.tzinfo is not None
                        and a.utcoffset() == timedelta(0)
                        and b - a == timedelta(minutes=15)
                        and (
                            prev_end is None
                            or a == prev_end
                        )
                    )
                except ValueError:
                    time_ok = False
                    b = None

                timeline_correct &= time_ok
                prev_end = b
                cumulative += energy_interval

                energy_correct &= all(
                    math.isfinite(v) and v >= 0
                    for v in (
                        power,
                        energy_interval,
                        cumulative_db,
                    )
                )
                energy_correct &= isclose(
                    energy_interval,
                    power * 0.25,
                    rel_tol=0,
                    abs_tol=1e-5,
                )
                energy_correct &= isclose(
                    cumulative_db,
                    cumulative,
                    rel_tol=0,
                    abs_tol=1e-4,
                )

            energy_correct &= isclose(
                energy,
                cumulative,
                rel_tol=0,
                abs_tol=1e-3,
            )

            pq_count = db.execute(
                "SELECT COUNT(*) FROM ges_pq_intervals "
                "WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]

            check(
                "PQ_PER_RUN:" + scenario,
                pq_count == (
                    0 if scenario == "BASELINE_NO_Q"
                    else 192
                ),
            )

        check("ENERGY_ACCOUNTING", energy_correct)
        check("TIMELINE_CONTINUITY", timeline_correct)

    return Acceptance(
        not issues,
        checks,
        tuple(issues),
        {
            "scenario_count": len(names),
            "db_rows": counts,
            "manifest_sha256": _sha256(manifest_path),
            "csv_sha256": _sha256(csv_path),
            "db_sha256": _sha256(db_path),
            "scope": "SYNTHETIC_SIMULATION_ONLY",
            "oem_calibration": "NOT_VERIFIED",
            "field_validation": "NOT_VERIFIED",
        },
    )


def compare_power_csv(path: str | Path) -> dict:
    """Compare aligned 15-minute predicted and observed power.

    CSV: timestamp_utc,predicted_kw,measured_kw
    Column names alone do not prove genuine field measurements.
    """
    stamps: list[datetime] = []
    predicted: list[float] = []
    observed: list[float] = []

    with Path(path).open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)

        if not {
            "timestamp_utc", "predicted_kw", "measured_kw"
        } <= set(reader.fieldnames or ()):
            raise ValueError(
                "Missing comparison CSV columns"
            )

        for row in reader:
            t = datetime.fromisoformat(
                row["timestamp_utc"].replace(
                    "Z", "+00:00"
                )
            )
            p = float(row["predicted_kw"])
            m = float(row["measured_kw"])

            if (
                t.tzinfo is None
                or t.utcoffset() != timedelta(0)
                or not all(
                    math.isfinite(x) and x >= 0
                    for x in (p, m)
                )
            ):
                raise ValueError(
                    "Comparison timestamps must be UTC, "
                    "values finite/nonnegative"
                )

            if (
                stamps
                and t - stamps[-1]
                != timedelta(minutes=15)
            ):
                raise ValueError(
                    "Noncontiguous / duplicate comparison timeline"
                )

            stamps.append(t)
            predicted.append(p)
            observed.append(m)

    if len(stamps) < 2:
        raise ValueError(
            "At least two 15-minute observations required"
        )

    differences = [
        p - m
        for p, m in zip(predicted, observed)
    ]
    n = len(differences)
    actual_energy = fsum(observed) * 0.25
    pred_energy = fsum(predicted) * 0.25

    return {
        "samples": n,
        "first_utc": stamps[0].isoformat(),
        "last_utc": stamps[-1].isoformat(),
        "mae_kw": fsum(
            abs(d) for d in differences
        ) / n,
        "rmse_kw": sqrt(
            fsum(d*d for d in differences) / n
        ),
        "bias_kw": fsum(differences) / n,
        "predicted_energy_kwh": pred_energy,
        "observed_energy_kwh": actual_energy,
        "energy_error_pct": (
            None if actual_energy == 0
            else 100 * (
                pred_energy - actual_energy
            ) / actual_energy
        ),
        "observation_provenance": "UNVERIFIED_USER_SUPPLIED_CSV",
        "site_validated": False,
    }

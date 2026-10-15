"""Offline *screening*, not OEM calibration or IEC/site certification.

No live API, no field network access, no commands, no model mutation.
The fit uses only the earlier training interval and evaluates a disjoint later holdout.
"""
from __future__ import annotations

import csv
import hashlib
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLANTS = {"GES": ("irradiance_w_m2", 0.0, 1600.0),
          "RES": ("wind_speed_m_s", 0.0, 80.0),
          "HES": ("flow_m3_s", 0.0, 5000.0)}
SOURCES = {"SYNTHETIC", "AUTHORIZED_FIELD_EXPORT"}
REQUIRED = {"timestamp_utc", "plant", "site_id", "equipment_id", "observed_kw",
            "predicted_kw", "quality", "source_kind", "source_id", "irradiance_w_m2",
            "wind_speed_m_s", "flow_m3_s"}
MAX_BYTES = 10 * 1024 * 1024


def _number(text: str, name: str, low: float = 0.0, high: float = 1e9) -> float:
    try:
        v = float(text)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueError(f"Invalid {name}") from e
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError(f"Out of range {name}")
    return v


def _time(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as e:
        raise ValueError("Invalid ISO timestamp") from e
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError("UTC offset is required, not a naive/local timestamp")
    return dt.astimezone(timezone.utc)


def _metrics(rows, factor: float) -> dict:
    o = [r["observed_kw"] for r in rows]
    p = [r["predicted_kw"] * factor for r in rows]
    errors = [v - w for v, w in zip(p, o)]
    n = len(o)
    denom = math.fsum(o) / n
    mae = math.fsum(map(abs, errors)) / n
    rmse = math.sqrt(math.fsum(e * e for e in errors) / n)
    bias = math.fsum(errors) / n
    return {"count": n, "observed_mean_kw": round(denom, 6),
            "mae_kw": round(mae, 6), "rmse_kw": round(rmse, 6),
            "bias_kw": round(bias, 6),
            "nmae_fraction": round(mae / denom, 6) if denom > 0 else None,
            "bias_fraction": round(bias / denom, 6) if denom > 0 else None}


def _fit_nonnegative_scale(training: list[dict]) -> float:
    # Least squares multiplicative coefficient; TRAINING ROWS ONLY.
    den = math.fsum(r["predicted_kw"] ** 2 for r in training)
    if den <= 1e-12:
        raise ValueError("No positive model power on training window")
    f = math.fsum(r["predicted_kw"] * r["observed_kw"] for r in training) / den
    if not 0.5 <= f <= 1.5:
        raise ValueError("Implausible scale factor: independent model review required")
    return f


def validate_csv(path: Path, *, holdout_fraction: float = .25) -> dict:
    """Validate and compare per-equipment chronological holdouts; never certify a site.

    All data remain in a local CSV supplied by the operator. No automatic OEM
    authenticity, transducer traceability, field-acceptance or IEC compliance.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Input must be an existing ordinary CSV, not a symlink")
    if not 0.20 <= holdout_fraction <= 0.40 or isinstance(holdout_fraction, bool):
        raise ValueError("Holdout fraction must be between .20 and .40")
    if path.stat().st_size > MAX_BYTES or path.stat().st_size == 0:
        raise ValueError("CSV file outside supported size")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Duplicate or missing column names")
        if not REQUIRED <= set(reader.fieldnames):
            raise ValueError("Missing CSV columns: " + ",".join(sorted(REQUIRED - set(reader.fieldnames))))
        rows = list(reader)
    if not 16 <= len(rows) <= 50000:
        raise ValueError("CSV requires 16..50000 observations")
    groups: dict[tuple[str,str,str], list[dict]] = {}
    sources = set()
    for row in rows:
        plant = row["plant"]
        if plant not in PLANTS:
            raise ValueError("Unknown plant")
        if not row["site_id"] or not row["equipment_id"] or not row["source_id"]:
            raise ValueError("Site, equipment and source IDs are mandatory")
        if row["quality"] != "GOOD":
            raise ValueError("Bad data quality cannot be used in performance screen")
        if row["source_kind"] not in SOURCES:
            raise ValueError("Invalid declared origin")
        sources.add(row["source_kind"])
        context, lo, hi = PLANTS[plant]
        ctx = _number(row[context], context, lo, hi)
        datum = {"timestamp": _time(row["timestamp_utc"]),
                 "observed_kw": _number(row["observed_kw"], "observed_kw"),
                 "predicted_kw": _number(row["predicted_kw"], "predicted_kw"),
                 "context": ctx, "source_id": row["source_id"]}
        groups.setdefault((row["site_id"], plant, row["equipment_id"]), []).append(datum)
    if len(sources) != 1:
        raise ValueError("Synthetic and field-labelled rows cannot mix")
    if len(groups) > 100:
        raise ValueError("Too many equipment groups")
    results = []
    for (site, plant, equipment), samples in sorted(groups.items()):
        if len(samples) < 16:
            raise ValueError("Each equipment needs >=16 records")
        times = [x["timestamp"] for x in samples]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("Timestamp order/uniqueness violation")
        gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
        if any(g > 86400 for g in gaps):
            raise ValueError("Gap >24h: unsuitable continuous comparison")
        ntest = max(4, math.ceil(len(samples) * holdout_fraction))
        training, holdout = samples[:-ntest], samples[-ntest:]
        if len(training) < 12:
            raise ValueError("Insufficient training samples")
        factor = _fit_nonnegative_scale(training)
        baseline = _metrics(holdout, 1.0)
        fitted = _metrics(holdout, factor)
        # These are self-chosen *screening* bounds, NOT standard thresholds.
        quality_screen = bool(fitted["nmae_fraction"] is not None
                              and fitted["nmae_fraction"] <= .15
                              and abs(fitted["bias_fraction"]) <= .10)
        results.append({"site_id":site, "plant":plant, "equipment_id":equipment,
                        "train_count":len(training), "holdout_count":len(holdout),
                        "holdout_start_utc":holdout[0]["timestamp"].isoformat(),
                        "holdout_end_utc":holdout[-1]["timestamp"].isoformat(),
                        "scale_train_only":round(factor, 8),
                        "baseline_holdout":baseline, "fitted_holdout":fitted,
                        "screening_thresholds": {"nmae_max": .15, "abs_bias_max": .10,
                                                 "origin":"PROJECT_DEFINED_NOT_STANDARD"},
                        "quality_screen_passed":quality_screen,
                        "context_range": [min(r["context"] for r in samples), max(r["context"] for r in samples)],
                        "measured_source_ids":sorted(set(r["source_id"] for r in samples)),
                        "external_calibration_verified":False,
                        "site_acceptance_verified":False})
    return {"scope":"OFFLINE_HOLDOUT_MODEL_SCREENING_ONLY", "csv_sha256":digest,
            "declared_source_kind":next(iter(sources)), "source_authenticated":False,
            "independently_oem_calibrated":False, "site_validated":False,
            "real_control_ready":False,
            "data_warning":"Origin strings and hash do not prove field authenticity",
            "groups":results, "all_quality_screens_passed":all(r["quality_screen_passed"] for r in results)}

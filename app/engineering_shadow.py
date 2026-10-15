"""Offline CSV comparison; no live OT sockets or control capabilities.

Rows: timestamp_utc, observed_kw, predicted_kw.
Any claimed measurement provenance is user supplied and NOT independently verified.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from math import fsum, sqrt, isfinite
from pathlib import Path
from typing import TextIO


def compare_stream(stream: TextIO, *, max_rows: int = 200000):
    reader = csv.DictReader(stream)
    expected = {'timestamp_utc', 'observed_kw', 'predicted_kw'}
    if not reader.fieldnames or not expected <= set(reader.fieldnames):
        raise ValueError('CSV needs timestamp_utc, observed_kw, predicted_kw')
    residuals = []
    targets = []
    times = []
    for row in reader:
        if len(residuals) >= max_rows:
            raise ValueError('Maximum CSV rows exceeded')
        try:
            time = datetime.fromisoformat(row['timestamp_utc'].replace('Z', '+00:00'))
            actual, predicted = float(row['observed_kw']), float(row['predicted_kw'])
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('Invalid CSV row') from exc
        if time.tzinfo is None or time.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError('Explicit UTC timestamps required')
        if not all(isfinite(x) and x >= 0 for x in (actual, predicted)):
            raise ValueError('Nonfinite or negative power')
        if times and time <= times[-1]:
            raise ValueError('CSV time not strictly increasing')
        times.append(time)
        targets.append(actual)
        residuals.append(predicted - actual)
    if len(residuals) < 2:
        raise ValueError('At least two rows required')
    n = len(residuals)
    return {'scope': 'OFFLINE_CSV_RESEARCH_COMPARISON',
            'rows': n,
            'mae_kw': fsum(map(abs, residuals)) / n,
            'rmse_kw': sqrt(fsum(e*e for e in residuals)/n),
            'bias_kw': fsum(residuals)/n,
            'observed_mean_kw': fsum(targets)/n,
            'first_utc': times[0].isoformat(),
            'last_utc': times[-1].isoformat(),
            'field_data_independently_verified': False,
            'calibrated_oem_model': False,
            'approved_for_plant_control': False,
            'warning': 'Observed values are user-provided; origin, meter calibration and data permissions not verified.'}


def compare_file(path: str | Path, *, max_bytes: int = 8_000_000):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError('Missing/oversized CSV file')
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return compare_stream(handle)

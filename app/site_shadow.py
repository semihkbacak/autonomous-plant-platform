"""Offline, read-only plant telemetry staging for engineering validation.

CSV is user-supplied and NEVER establishes equipment calibration, trust or
control authority. This module makes zero network/device connections.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable

FIELDS = ("site_id", "plant", "equipment_id", "metric", "unit", "timestamp_utc", "value", "quality", "source_ref")
IDENT = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
# Engineering-level plausibility limits, NOT equipment setpoints or protective thresholds.
METRICS = {
    "active_power_kw": ("kW", 0, 2_000_000),
    "frequency_hz": ("Hz", 0, 100),
    "rpm": ("rpm", 0, 30_000),
    "flow_m3_s": ("m3/s", 0, 100_000),
    "net_head_m": ("m", 0, 2_000),
    "vibration_mm_s": ("mm/s", 0, 500),
    "bearing_temperature_c": ("C", -70, 300),
    "irradiance_w_m2": ("W/m2", 0, 2_000),
    "dc_voltage_v": ("V", 0, 2_500),
    "dc_current_a": ("A", 0, 100_000),
    "wind_speed_m_s": ("m/s", 0, 100),
    "pitch_angle_deg": ("deg", -180, 180),
    "yaw_error_deg": ("deg", -180, 180),
}
PLANT_METRICS = {
    "HES": {"active_power_kw", "frequency_hz", "rpm", "flow_m3_s", "net_head_m", "vibration_mm_s", "bearing_temperature_c"},
    "GES": {"active_power_kw", "frequency_hz", "irradiance_w_m2", "dc_voltage_v", "dc_current_a"},
    "RES": {"active_power_kw", "frequency_hz", "rpm", "wind_speed_m_s", "pitch_angle_deg", "yaw_error_deg", "vibration_mm_s", "bearing_temperature_c"},
}


@dataclass(frozen=True)
class Reading:
    site_id: str
    plant: str
    equipment_id: str
    metric: str
    unit: str
    timestamp_utc: str
    value: float
    quality: str
    source_ref: str


def parse_utc(value: str) -> datetime:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid ISO8601 timestamp") from exc
    if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
        raise ValueError("Explicit UTC timezone required")
    return ts.astimezone(timezone.utc)


def validate_reading(raw: dict, *, now: datetime | None = None) -> Reading:
    for key in ("site_id", "equipment_id"):
        if not IDENT.fullmatch(str(raw.get(key, ""))):
            raise ValueError(f"Invalid {key}")
    plant, metric, quality = (str(raw.get(k, "")) for k in ("plant", "metric", "quality"))
    if plant not in PLANT_METRICS or metric not in PLANT_METRICS[plant]:
        raise ValueError("Unknown plant/metric combination")
    unit, lower, upper = METRICS[metric]
    if raw.get("unit") != unit:
        raise ValueError(f"Wrong unit for {metric}; expected {unit}")
    if quality not in {"GOOD", "BAD", "UNCERTAIN"}:
        raise ValueError("Unknown source quality flag")
    ref = str(raw.get("source_ref", ""))
    if not 1 <= len(ref) <= 120 or any(ord(c) < 32 for c in ref):
        raise ValueError("Invalid source reference")
    try:
        v = float(raw.get("value", ""))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid numeric measurement") from exc
    if not math.isfinite(v) or not lower <= v <= upper:
        raise ValueError("Nonfinite or physically implausible measurement")
    ts = parse_utc(str(raw.get("timestamp_utc", "")))
    clock = now or datetime.now(timezone.utc)
    if ts > clock + timedelta(minutes=2):
        raise ValueError("Future measurement timestamp")
    return Reading(str(raw["site_id"]), plant, str(raw["equipment_id"]), metric, unit,
                   ts.isoformat(), v, quality, ref)


class ShadowStore:
    """Atomic SQLite ingestion of approved *offline exports*, never control."""
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    @contextmanager
    def _connect(self, *, existing: bool = False):
        if existing and not self.path.is_file():
            raise FileNotFoundError("No offline telemetry database")
        if not existing:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(
            self.path.resolve().as_uri() + "?mode=ro" if existing else str(self.path),
            uri=existing, timeout=10,
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            if not existing:
                db.commit()
        except BaseException:
            if not existing:
                db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS offline_readings (
                  site_id TEXT NOT NULL, plant TEXT NOT NULL,
                  equipment_id TEXT NOT NULL, metric TEXT NOT NULL,
                  timestamp_utc TEXT NOT NULL, unit TEXT NOT NULL,
                  value REAL NOT NULL, quality TEXT NOT NULL, source_ref TEXT NOT NULL,
                  PRIMARY KEY (site_id, plant, equipment_id, metric, timestamp_utc)
                );
                CREATE INDEX IF NOT EXISTS ix_offline_latest
                ON offline_readings(site_id, plant, timestamp_utc DESC);
            """)

    def import_csv(self, file: str | Path, *, max_bytes: int = 10_000_000,
                   max_rows: int = 100_000, now: datetime | None = None) -> dict:
        file = Path(file)
        if not file.is_file() or file.stat().st_size > max_bytes:
            raise ValueError("CSV missing or exceeds configured size")
        self.initialize()
        count = 0
        latest: dict[tuple, datetime] = {}
        # The entire batch is atomic. No silent sorting, coercion or overwriting.
        with file.open("r", encoding="utf-8-sig", newline="") as stream, self._connect() as db:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or set(reader.fieldnames) != set(FIELDS):
                raise ValueError("CSV columns do not match offline telemetry schema")
            db.execute("BEGIN IMMEDIATE")
            for row in reader:
                count += 1
                if count > max_rows:
                    raise ValueError("Too many measurements")
                r = validate_reading(row, now=now)
                key = (r.site_id, r.plant, r.equipment_id, r.metric)
                ts = parse_utc(r.timestamp_utc)
                prev = latest.get(key)
                if prev is None:
                    prev_raw = db.execute(
                        "SELECT MAX(timestamp_utc) FROM offline_readings "
                        "WHERE site_id=? AND plant=? AND equipment_id=? AND metric=?", key,
                    ).fetchone()[0]
                    prev = parse_utc(prev_raw) if prev_raw else None
                if prev is not None and ts <= prev:
                    raise ValueError("Out-of-order or duplicate stream measurement")
                latest[key] = ts
                db.execute(
                    "INSERT INTO offline_readings VALUES(?,?,?,?,?,?,?,?,?)",
                    (r.site_id, r.plant, r.equipment_id, r.metric, r.timestamp_utc,
                     r.unit, r.value, r.quality, r.source_ref),
                )
            if not count:
                raise ValueError("Empty measurement CSV")
            db.commit()
        return {"rows_imported": count, "streams": len(latest),
                "scope": "USER_PROVIDED_OFFLINE_EXPORT_NOT_FIELD_VERIFIED",
                "ot_control_enabled": False}

    def latest(self, *, site_id: str | None = None, now: datetime | None = None,
               max_age_seconds: int = 300) -> dict:
        if not 1 <= max_age_seconds <= 86400:
            raise ValueError("Invalid freshness window")
        if site_id is not None and not IDENT.fullmatch(site_id):
            raise ValueError("Invalid site ID")
        out = {"scope": "OFFLINE_SHADOW_UNVERIFIED_NO_OT_COMMANDS",
               "source_independently_verified": False,
               "controls_allowed": False, "telemetry_live": False,
               "freshness_window_s": max_age_seconds, "measurements": [],
               "ready_for_plant_control": False}
        if not self.path.is_file():
            out["status"] = "NO_DATA"
            return out
        clock = now or datetime.now(timezone.utc)
        with self._connect(existing=True) as db:
            rows = db.execute("""
                SELECT r.* FROM offline_readings r WHERE
                (? IS NULL OR r.site_id=?) AND r.timestamp_utc = (
                    SELECT MAX(r2.timestamp_utc) FROM offline_readings r2
                    WHERE r2.site_id=r.site_id AND r2.plant=r.plant
                      AND r2.equipment_id=r.equipment_id AND r2.metric=r.metric
                ) ORDER BY r.site_id,r.plant,r.equipment_id,r.metric
            """, (site_id, site_id)).fetchall()
        for row in rows:
            d = dict(row)
            age = (clock - parse_utc(d["timestamp_utc"])).total_seconds()
            d["age_seconds"] = max(0, round(age, 3))
            d["freshness"] = "FRESH_OFFLINE_EXPORT" if 0 <= age <= max_age_seconds else "STALE"
            d["usable_for_study"] = d["quality"] == "GOOD" and d["freshness"] == "FRESH_OFFLINE_EXPORT"
            out["measurements"].append(d)
        out["status"] = "OFFLINE_EXPORT_REVIEW_REQUIRED" if rows else "NO_DATA"
        out["all_usable_for_study"] = bool(rows) and all(r["usable_for_study"] for r in out["measurements"])
        return out

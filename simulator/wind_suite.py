"""RES v0.6–v0.9: reproducible 12-case scenario matrix & long horizon."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import cos, pi, sin

from simulator.wind_physics import WindControl, WindFarm, WindTurbine, WindWeather

CASES = (
    'BASELINE', 'WAKE_DOWNWIND', 'LOW_WIND', 'HIGH_WIND_RESTART',
    'GRID_LOSS', 'EMERGENCY_STOP', 'TURBINE_FAULT', 'MAINTENANCE',
    'YAW_MISALIGNMENT', 'ICING_DERATE', 'ACTIVE_CURTAILMENT', 'GUSTS',
)


def default_farm() -> WindFarm:
    return WindFarm((
        WindTurbine('WT_1', x_m=0, y_m=0),
        WindTurbine('WT_2', x_m=600, y_m=0),
    ))


def run_scenario(name: str, days: int = 1) -> list:
    if name not in CASES or type(days) is not int or not 1 <= days <= 365:
        raise ValueError('Unknown scenario or invalid days')
    farm = default_farm()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = []
    for n in range(days * 96):
        phase = (n % 96) / 96
        season = sin(2 * pi * n / (365 * 96))
        speed = max(0, 7.0 + 1.9 * sin(2 * pi * phase) + 1.7 * season)
        direction = 0 if name != 'WAKE_DOWNWIND' else 270
        if name == 'LOW_WIND':
            speed = 1.0
        if name == 'HIGH_WIND_RESTART':
            speed = 28.0 if (n % 96) in range(32, 49) else 9.0
        if name == 'GUSTS':
            speed = 18.0 if (n % 96) % 8 == 0 else speed
        w = WindWeather(
            start + timedelta(minutes=15 * (n + 1)), speed, direction,
            temperature_c=12 + 12 * season,
        )
        active_event = (n % 96) >= 32 and (n % 96) < 64
        control = WindControl(
            grid_available=not (name == 'GRID_LOSS' and active_event),
            emergency_stop=name == 'EMERGENCY_STOP' and active_event,
            fault_ids=frozenset({'WT_1'}) if name == 'TURBINE_FAULT' and active_event else frozenset(),
            maintenance_ids=frozenset({'WT_2'}) if name == 'MAINTENANCE' and active_event else frozenset(),
            yaw_error_deg={'WT_1': 45.0} if name == 'YAW_MISALIGNMENT' else {},
            icing_fraction={'WT_2': 0.5} if name == 'ICING_DERATE' else {},
            target_kw=800.0 if name == 'ACTIVE_CURTAILMENT' else None,
        )
        results.append(farm.step(w, control))
    return results


def long_horizon(days: int = 365) -> dict:
    """No SQLite writes; deterministic 15-min screening, not an OEM study."""
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError('days must be 1..365')
    # Generate one streaming iteration, avoid duplicate DB writes.
    farm = default_farm()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    total = peak = 0.0
    for i in range(days * 96):
        season = sin(2 * pi * i / (365 * 96))
        day = sin(2 * pi * (i % 96) / 96)
        weather = WindWeather(
            start + timedelta(minutes=15 * (i + 1)),
            max(0.0, 7.5 + 1.8 * day + 2.5 * season),
            270 if (i // 96) % 2 else 0,
            temperature_c=12 + 14 * season,
        )
        report = farm.step(weather)
        total += report.energy_kwh
        peak = max(peak, report.farm_dispatched_kw)
    return {
        'days': days, 'interval_count': days * 96,
        'energy_kwh': total, 'peak_kw': peak,
        'scope': 'SYNTHETIC_15MIN_WIND_POWER_NO_OEM_OR_FIELD_VALIDATION',
        'passed': total >= 0 and peak <= 6000,
    }

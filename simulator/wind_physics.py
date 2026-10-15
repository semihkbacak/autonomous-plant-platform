"""RES v0.1–v0.4: synthetic, deterministic, simulator-only wind farm.

No OEM power curve, IEC design/load assessment or OT controls are implied.
15-minute interval power is treated as constant across the interval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import cos, isfinite, pi, radians, sin, sqrt
from typing import Mapping


def finite(name: str, value: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f"{name}: expected finite number")
    if not low <= value <= high:
        raise ValueError(f"{name}: out of supported range [{low}, {high}]")
    return float(value)


@dataclass(frozen=True)
class WindTurbine:
    turbine_id: str
    rated_kw: float = 3000.0
    rotor_diameter_m: float = 100.0
    hub_height_m: float = 90.0
    x_m: float = 0.0  # Easting relative to site origin
    y_m: float = 0.0  # Northing relative to site origin
    cut_in_m_s: float = 3.0
    rated_m_s: float = 12.0
    cut_out_m_s: float = 25.0
    restart_m_s: float = 20.0

    def __post_init__(self) -> None:
        if not self.turbine_id.strip():
            raise ValueError("Turbine ID required")
        finite("rated_kw", self.rated_kw, 1, 30000)
        finite("rotor_diameter_m", self.rotor_diameter_m, 5, 300)
        finite("hub_height_m", self.hub_height_m, 5, 300)
        finite("x_m", self.x_m, -1e7, 1e7)
        finite("y_m", self.y_m, -1e7, 1e7)
        if not (0 <= self.cut_in_m_s < self.rated_m_s < self.cut_out_m_s <= 60):
            raise ValueError("Invalid cut-in/rated/cut-out thresholds")
        if not (self.cut_in_m_s < self.restart_m_s < self.cut_out_m_s):
            raise ValueError("Restart threshold must be between cut-in and cut-out")


@dataclass(frozen=True)
class WindWeather:
    end_utc: datetime
    speed_m_s: float  # Wind at reference height
    from_direction_deg: float  # meteorological: 0=N, 270=W
    temperature_c: float = 15.0
    pressure_pa: float = 101325.0
    reference_height_m: float = 10.0
    shear_exponent: float = 0.14

    def __post_init__(self) -> None:
        if self.end_utc.tzinfo is None or self.end_utc.utcoffset() != timedelta(0):
            raise ValueError("Weather timestamp must be timezone-aware UTC")
        for n, v, a, b in (
            ("speed_m_s", self.speed_m_s, 0, 70),
            ("from_direction_deg", self.from_direction_deg, 0, 360),
            ("temperature_c", self.temperature_c, -70, 65),
            ("pressure_pa", self.pressure_pa, 60000, 115000),
            ("reference_height_m", self.reference_height_m, 1, 300),
            ("shear_exponent", self.shear_exponent, 0, 0.6),
        ):
            finite(n, v, a, b)


@dataclass(frozen=True)
class WindControl:
    grid_available: bool = True
    emergency_stop: bool = False
    maintenance_ids: frozenset[str] = frozenset()
    fault_ids: frozenset[str] = frozenset()
    target_kw: float | None = None
    yaw_error_deg: Mapping[str, float] = field(default_factory=dict)
    icing_fraction: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TurbineReading:
    turbine_id: str
    status: str
    hub_wind_m_s: float
    effective_wind_m_s: float
    wake_loss_fraction: float
    available_kw: float
    dispatched_kw: float
    curtailed_kw: float
    rotor_rpm_proxy: float
    high_wind_latched: bool


@dataclass(frozen=True)
class WindInterval:
    end_utc: datetime
    source_kind: str
    farm_available_kw: float
    farm_dispatched_kw: float
    farm_curtailed_kw: float
    energy_kwh: float
    unserved_target_kw: float
    turbines: tuple[TurbineReading, ...]


def air_density_kg_m3(temperature_c: float, pressure_pa: float) -> float:
    finite("temperature_c", temperature_c, -70, 65)
    finite("pressure_pa", pressure_pa, 60000, 115000)
    return pressure_pa / (287.05 * (temperature_c + 273.15))


def hub_wind(weather: WindWeather, turbine: WindTurbine) -> float:
    return weather.speed_m_s * (
        turbine.hub_height_m / weather.reference_height_m
    ) ** weather.shear_exponent


def synthetic_power_kw(turbine: WindTurbine, speed_m_s: float, density: float) -> float:
    """Synthetic cubic ramp, capped at nameplate, not a manufacturer P(v)."""
    finite("speed_m_s", speed_m_s, 0, 100)
    finite("density", density, 0.5, 1.7)
    if speed_m_s < turbine.cut_in_m_s or speed_m_s >= turbine.cut_out_m_s:
        return 0.0
    fraction = (speed_m_s**3 - turbine.cut_in_m_s**3) / (
        turbine.rated_m_s**3 - turbine.cut_in_m_s**3
    )
    return turbine.rated_kw * min(1.0, max(0.0, fraction * density / 1.225))


def wake_adjusted_speeds(
    turbines: tuple[WindTurbine, ...], weather: WindWeather
) -> dict[str, float]:
    """Simple Jensen top-hat wake; largest single upstream deficit only.

    This is a screening proxy, not CFD, IEC wake validation or turbulence model.
    """
    theta = radians(weather.from_direction_deg)
    down_x, down_y = -sin(theta), -cos(theta)
    result: dict[str, float] = {}
    for down in turbines:
        base = hub_wind(weather, down)
        max_deficit = 0.0
        for up in turbines:
            if up.turbine_id == down.turbine_id:
                continue
            dx, dy = down.x_m - up.x_m, down.y_m - up.y_m
            along = dx * down_x + dy * down_y
            cross = abs(-dx * down_y + dy * down_x)
            if along <= 0:
                continue
            wake_radius = up.rotor_diameter_m / 2 + 0.05 * along
            if cross > wake_radius:
                continue
            deficit = (1 - sqrt(1 - 0.8)) / (
                1 + 2 * 0.05 * along / up.rotor_diameter_m
            ) ** 2
            max_deficit = max(max_deficit, deficit)
        result[down.turbine_id] = base * (1 - max_deficit)
    return result


class WindFarm:
    """Simulation-only farm, with high-wind trip hysteresis per turbine."""

    def __init__(self, turbines: tuple[WindTurbine, ...]):
        ids = [t.turbine_id for t in turbines]
        if not turbines or len(ids) != len(set(ids)):
            raise ValueError("At least one uniquely identified turbine required")
        if len({(t.x_m, t.y_m) for t in turbines}) != len(turbines):
            raise ValueError("Turbine positions must differ")
        self.turbines = turbines
        self._tripped = {tid: False for tid in ids}
        self._last_time: datetime | None = None

    def step(self, weather: WindWeather, control: WindControl = WindControl()) -> WindInterval:
        ids = set(self._tripped)
        if (control.fault_ids | control.maintenance_ids) - ids:
            raise ValueError("Unknown turbine fault/maintenance ID")
        if set(control.yaw_error_deg) - ids or set(control.icing_fraction) - ids:
            raise ValueError("Unknown turbine curve modifier ID")
        for key, value in control.yaw_error_deg.items():
            finite(f"yaw[{key}]", value, -90, 90)
        for key, value in control.icing_fraction.items():
            finite(f"icing[{key}]", value, 0, 1)
        if control.target_kw is not None:
            finite("target_kw", control.target_kw, 0, 1e9)
        if self._last_time is not None and weather.end_utc - self._last_time != timedelta(minutes=15):
            raise ValueError("Expected contiguous 15-minute UTC intervals")

        speeds = wake_adjusted_speeds(self.turbines, weather)
        density = air_density_kg_m3(weather.temperature_c, weather.pressure_pa)
        pending_tripped = dict(self._tripped)
        draft = []
        for turbine in self.turbines:
            tid = turbine.turbine_id
            effective = speeds[tid]
            hub = hub_wind(weather, turbine)
            if effective >= turbine.cut_out_m_s:
                pending_tripped[tid] = True
            elif effective <= turbine.restart_m_s:
                pending_tripped[tid] = False

            blocked = (
                not control.grid_available or control.emergency_stop
                or tid in control.fault_ids or tid in control.maintenance_ids
            )
            if blocked:
                status, available = "BLOCKED", 0.0
            elif pending_tripped[tid]:
                status, available = "HIGH_WIND_LATCHED", 0.0
            elif effective < turbine.cut_in_m_s:
                status, available = "LOW_WIND", 0.0
            else:
                status = "RUNNING"
                available = synthetic_power_kw(turbine, effective, density)
                yaw = abs(control.yaw_error_deg.get(tid, 0.0))
                available *= cos(radians(yaw)) ** 1.88
                available *= (1 - control.icing_fraction.get(tid, 0.0))
            draft.append((turbine, hub, effective, status, available, pending_tripped[tid]))

        total = sum(x[4] for x in draft)
        target = total if control.target_kw is None else min(total, control.target_kw)
        readings = []
        for turbine, hub, effective, status, available, tripped in draft:
            dispatched = target * available / total if total > 0 else 0.0
            curtailed = max(0.0, available - dispatched)
            if curtailed > 1e-8 and status == "RUNNING":
                status = "CURTAILED"
            rpm = min(22.0, 60.0 * 7.0 * effective / (pi * turbine.rotor_diameter_m)) if dispatched > 0 else 0.0
            readings.append(TurbineReading(
                turbine.turbine_id, status, hub, effective,
                max(0.0, 1 - effective / hub) if hub > 0 else 0.0,
                available, dispatched, curtailed, rpm, tripped,
            ))
        # State changes occur only after all validation/calculation completes.
        self._tripped = pending_tripped
        self._last_time = weather.end_utc
        return WindInterval(
            weather.end_utc, "SYNTHETIC_WIND_SIMULATION_NOT_OEM", total,
            sum(x.dispatched_kw for x in readings),
            sum(x.curtailed_kw for x in readings),
            sum(x.dispatched_kw for x in readings) * 0.25,
            0.0 if control.target_kw is None else max(0.0, control.target_kw - target),
            tuple(readings),
        )

"""Solar resource to plane-of-array (POA) irradiance conversion.

Simulator-only foundation. Uses published pvlib solar-position and
Perez-Driesse sky transposition methods. This is NOT a complete PV energy
model: shading, spectral and angle-of-incidence losses are not included.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

import pandas as pd
import pvlib


@dataclass(frozen=True)
class SolarSite:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0


@dataclass(frozen=True)
class PVSurface:
    tilt_deg: float
    azimuth_deg: float
    albedo: float = 0.20


@dataclass(frozen=True)
class IrradianceSample:
    timestamp: datetime
    ghi_w_m2: float
    dni_w_m2: float
    dhi_w_m2: float
    source_type: str = "SYNTHETIC"


@dataclass(frozen=True)
class POAResult:
    timestamp_utc: datetime
    apparent_zenith_deg: float
    solar_azimuth_deg: float
    poa_global_w_m2: float
    poa_direct_w_m2: float
    poa_sky_diffuse_w_m2: float
    poa_ground_diffuse_w_m2: float
    sun_above_horizon: bool
    source_type: str
    quality_flags: tuple[str, ...]
    transposition_model: str = "perez-driesse"


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _validate(site: SolarSite, surface: PVSurface, sample: IrradianceSample) -> datetime:
    lat = _finite(site.latitude_deg, "latitude_deg")
    lon = _finite(site.longitude_deg, "longitude_deg")
    _finite(site.altitude_m, "altitude_m")
    tilt = _finite(surface.tilt_deg, "tilt_deg")
    azimuth = _finite(surface.azimuth_deg, "azimuth_deg")
    albedo = _finite(surface.albedo, "albedo")

    if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
        raise ValueError("site latitude/longitude is out of range")
    if not 0.0 <= tilt <= 90.0:
        raise ValueError("surface tilt must be between 0 and 90 degrees")
    if not 0.0 <= azimuth < 360.0:
        raise ValueError("surface azimuth must be in [0, 360) degrees")
    if not 0.0 <= albedo <= 1.0:
        raise ValueError("albedo must be between 0 and 1")

    for name in ("ghi_w_m2", "dni_w_m2", "dhi_w_m2"):
        if _finite(getattr(sample, name), name) < 0.0:
            raise ValueError(f"{name} cannot be negative")

    if not isinstance(sample.timestamp, datetime) or sample.timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    if sample.timestamp.utcoffset() is None:
        raise ValueError("timestamp needs a valid UTC offset")
    if sample.source_type not in {"SYNTHETIC", "MEASURED", "SATELLITE", "REANALYSIS", "FORECAST"}:
        raise ValueError("source_type is not recognized")

    return sample.timestamp.astimezone(timezone.utc)


def calculate_poa(
    site: SolarSite,
    surface: PVSurface,
    sample: IrradianceSample,
) -> POAResult:
    """Convert GHI, DNI, DHI to tilted-plane irradiance.

    Assumptions: fixed-tilt, unobstructed surface, isotropic ground reflection;
    Perez-Driesse for diffuse sky. Time must have a timezone. Directions use
    pvlib conventions: north=0, east=90, south=180, west=270 degrees.

    No measured resource data are created or fetched by this function.
    """
    timestamp_utc = _validate(site, surface, sample)
    times = pd.DatetimeIndex([timestamp_utc])
    sun = pvlib.solarposition.get_solarposition(
        times,
        latitude=float(site.latitude_deg),
        longitude=float(site.longitude_deg),
        altitude=float(site.altitude_m),
    )
    zenith = float(sun["apparent_zenith"].iloc[0])
    azimuth = float(sun["azimuth"].iloc[0])

    flags: list[str] = []
    if zenith >= 90.0:
        if max(sample.ghi_w_m2, sample.dni_w_m2, sample.dhi_w_m2) > 0.0:
            flags.append("NONZERO_IRRADIANCE_WHILE_SUN_BELOW_HORIZON")
        return POAResult(
            timestamp_utc, zenith, azimuth,
            0.0, 0.0, 0.0, 0.0,
            False, sample.source_type, tuple(flags),
        )

    # A useful data-quality diagnostic; no arbitrary rejection of measurements.
    # For consistent simultaneous GHI/DNI/DHI, closure error is near zero.
    from math import cos, radians
    predicted_ghi = sample.dhi_w_m2 + sample.dni_w_m2 * max(0.0, cos(radians(zenith)))
    if abs(sample.ghi_w_m2 - predicted_ghi) > max(50.0, 0.15 * max(1.0, sample.ghi_w_m2)):
        flags.append("HORIZONTAL_IRRADIANCE_CLOSURE_WARNING")

    dni_extra = float(pvlib.irradiance.get_extra_radiation(times).iloc[0])
    components = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface.tilt_deg,
        surface_azimuth=surface.azimuth_deg,
        solar_zenith=zenith,
        solar_azimuth=azimuth,
        dni=sample.dni_w_m2,
        ghi=sample.ghi_w_m2,
        dhi=sample.dhi_w_m2,
        dni_extra=dni_extra,
        albedo=surface.albedo,
        model="perez-driesse",
    )

    def physical(name: str) -> float:
        raw = float(components[name])
        if not isfinite(raw):
            raise ValueError(f"pvlib calculated non-finite {name}")
        if raw < -1e-6:
            raise ValueError(f"pvlib calculated negative {name}")
        return max(0.0, raw)

    return POAResult(
        timestamp_utc=timestamp_utc,
        apparent_zenith_deg=zenith,
        solar_azimuth_deg=azimuth,
        poa_global_w_m2=physical("poa_global"),
        poa_direct_w_m2=physical("poa_direct"),
        poa_sky_diffuse_w_m2=physical("poa_sky_diffuse"),
        poa_ground_diffuse_w_m2=physical("poa_ground_diffuse"),
        sun_above_horizon=True,
        source_type=sample.source_type,
        quality_flags=tuple(flags),
    )

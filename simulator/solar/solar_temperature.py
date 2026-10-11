"""Faiman PV temperature layer; simulation only, no field controls.

References:
- pvlib.temperature.faiman (pvlib 0.16.1 API)
- Faiman, D. (2008), Progress in Photovoltaics, 16, 307-315.

Note: Faiman describes an empirical cell/module temperature. The optional
cell-to-module offset is a demonstrative, separately calibrated correction;
its default is zero to avoid claiming an unverified temperature difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pvlib


@dataclass(frozen=True)
class FaimanParameters:
    u0_w_m2_k: float = 25.0
    u1_w_s_m3_k: float = 6.84
    cell_over_module_c_at_1000w_m2: float = 0.0


@dataclass(frozen=True)
class PVTemperature:
    module_temperature_c: float
    cell_temperature_c: float
    model: str = "faiman"


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def calculate_pv_temperature(
    poa_global_w_m2: float,
    ambient_temperature_c: float,
    wind_speed_m_s: float,
    params: FaimanParameters | None = None,
) -> PVTemperature:
    """Estimate module and cell temperature under POA irradiance.

    The wind speed must correspond to the measurement height for which
    u0/u1 were calibrated. The default u0/u1 are not plant-specific.
    """
    p = params if params is not None else FaimanParameters()
    irradiance = _number(poa_global_w_m2, "poa_global_w_m2")
    ambient = _number(ambient_temperature_c, "ambient_temperature_c")
    wind = _number(wind_speed_m_s, "wind_speed_m_s")
    u0 = _number(p.u0_w_m2_k, "u0_w_m2_k")
    u1 = _number(p.u1_w_s_m3_k, "u1_w_s_m3_k")
    correction = _number(p.cell_over_module_c_at_1000w_m2, "cell_over_module_c_at_1000w_m2")

    if irradiance < 0:
        raise ValueError("poa_global_w_m2 cannot be negative")
    if wind < 0:
        raise ValueError("wind_speed_m_s cannot be negative")
    if ambient <= -273.15:
        raise ValueError("ambient_temperature_c must be above absolute zero")
    if u0 <= 0 or u1 < 0:
        raise ValueError("Faiman coefficients require u0 > 0, u1 >= 0")
    if correction < 0:
        raise ValueError("cell_over_module_c_at_1000w_m2 cannot be negative")

    module = float(pvlib.temperature.faiman(
        poa_global=irradiance,
        temp_air=ambient,
        wind_speed=wind,
        u0=u0,
        u1=u1,
    ))
    cell = module + correction * irradiance / 1000.0
    if not isfinite(module) or not isfinite(cell) or cell <= -273.15:
        raise ValueError("PV temperature calculation is not physically valid")
    return PVTemperature(module_temperature_c=module, cell_temperature_c=cell)

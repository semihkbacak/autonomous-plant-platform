
"""
Independent MPPT DC calculations.

Uses APP's existing:
- PV irradiance/POA model
- Faiman temperature model
- De Soto single-diode DC model

Simulation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isfinite
from typing import Sequence

from simulator.solar.pv_array import (
    PVArrayConfiguration,
    PVArrayDCResult,
    calculate_pv_array_from_poa,
)

from simulator.solar.solar_resource import (
    PVSurface,
    SolarSite,
    POAResult,
    calculate_poa,
)

from simulator.solar.solar_pipeline import SolarWeather

from simulator.solar.solar_temperature import (
    FaimanParameters,
)


@dataclass(frozen=True)
class MPPTLimits:
    mppt_count: int
    min_v: float
    max_v: float
    max_dc_v: float
    max_operating_a: float
    max_short_circuit_a: float
    max_strings: int


@dataclass(frozen=True)
class MPPTArray:
    channel: int
    array: PVArrayConfiguration
    surface: PVSurface
    temperature_params: FaimanParameters = (
        FaimanParameters()
    )


@dataclass(frozen=True)
class MPPTChannelResult:
    channel: int

    voltage_v: float
    current_a: float
    short_circuit_a: float
    open_circuit_v: float

    offered_kw: float
    accepted_kw: float
    rejected_kw: float

    reasons: tuple[str, ...]
    poa: POAResult | None = None
    dc: PVArrayDCResult | None = None


@dataclass(frozen=True)
class MultiMPPTResult:
    channels: tuple[MPPTChannelResult, ...]

    dc_offered_kw: float
    dc_accepted_kw: float
    dc_rejected_kw: float

    warnings: tuple[str, ...]


def calculate_multi_mppt_dc(
    site: SolarSite,
    weather: SolarWeather,
    arrays: Sequence[MPPTArray],
    limits: MPPTLimits,
) -> MultiMPPTResult:
    """
    Calculate per-channel DC MPP and apply
    preliminary MPPT electrical limits.

    Current limiting is estimated at Vmp.
    This is not a complete MPPT control-loop
    or mismatch-curve model.
    """

    if (
        not arrays
        or type(limits.mppt_count) is not int
        or limits.mppt_count < 1
        or type(limits.max_strings) is not int
        or limits.max_strings < 1
    ):
        raise ValueError(
            "Invalid MPPT configuration"
        )

    electrical_limits = (
        limits.min_v,
        limits.max_v,
        limits.max_dc_v,
        limits.max_operating_a,
        limits.max_short_circuit_a,
    )

    if (
        any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
            for value in electrical_limits
        )
        or not (
            limits.min_v
            < limits.max_v
            <= limits.max_dc_v
        )
    ):
        raise ValueError(
            "Invalid MPPT electrical limits"
        )

    seen = set()
    results = []

    # Reuse POA for channels facing
    # exactly the same surface.
    poa_cache = {}

    for item in arrays:

        if (
            type(item.channel) is not int
            or not (
                1 <= item.channel <= limits.mppt_count
            )
        ):
            raise ValueError(
                "Invalid MPPT channel number"
            )

        if item.channel in seen:
            raise ValueError(
                "Duplicate MPPT channel"
            )

        seen.add(item.channel)

        if (
            item.array.parallel_strings
            > limits.max_strings
        ):
            raise ValueError(
                "Too many parallel strings on MPPT"
            )

        # 1. Irradiance for this MPPT surface.
        if item.surface not in poa_cache:
            poa_cache[item.surface] = calculate_poa(
                site=site,
                surface=item.surface,
                sample=weather.irradiance,
            )

        # 2. Independent PV array DC calculation.
        dc = calculate_pv_array_from_poa(
            poa_result=poa_cache[item.surface],

            ambient_temperature_c=(
                weather.ambient_temperature_c
            ),

            wind_speed_m_s=(
                weather.wind_speed_m_s
            ),

            config=item.array,
            temperature_params=item.temperature_params,
        )

        offered = dc.array_pmp_kw
        voltage = dc.array_vmp_v
        current = dc.array_imp_a

        isc = (
            dc.module_isc_a
            * item.array.parallel_strings
        )

        voc = (
            dc.module_voc_v
            * item.array.modules_per_string
        )

        reasons = []

        # 3. Apply channel-specific operating limits.
        if offered <= 0:
            accepted = 0.0

        elif voc > limits.max_dc_v:
            accepted = 0.0

            reasons.append(
                "DC_VOC_EXCEEDS_ABSOLUTE_LIMIT"
            )

        elif isc > limits.max_short_circuit_a:
            accepted = 0.0

            reasons.append(
                "MPPT_SHORT_CIRCUIT_CURRENT_LIMIT"
            )

        elif not (
            limits.min_v
            <= voltage
            <= limits.max_v
        ):
            accepted = 0.0

            reasons.append(
                "OUTSIDE_MPPT_WINDOW"
            )

        else:
            # Approximate current limitation at Vmp.
            maximum_power_kw = (
                voltage
                * limits.max_operating_a
                / 1000.0
            )

            accepted = min(
                offered,
                maximum_power_kw,
            )

            if current > limits.max_operating_a:
                reasons.append(
                    "MPPT_OPERATING_CURRENT_LIMIT_ESTIMATE"
                )

        results.append(
            MPPTChannelResult(
                channel=item.channel,

                voltage_v=voltage,
                current_a=current,

                short_circuit_a=isc,
                open_circuit_v=voc,

                offered_kw=offered,
                accepted_kw=accepted,

                rejected_kw=max(
                    0.0,
                    offered - accepted,
                ),

                reasons=tuple(reasons),
                poa=poa_cache[item.surface],
                dc=dc,
            )
        )

    # 4. Combine DC power, not DC voltages.
    total_offered = fsum(
        item.offered_kw
        for item in results
    )

    total_accepted = fsum(
        item.accepted_kw
        for item in results
    )

    return MultiMPPTResult(
        channels=tuple(results),

        dc_offered_kw=total_offered,
        dc_accepted_kw=total_accepted,

        dc_rejected_kw=max(
            0.0,
            total_offered - total_accepted,
        ),

        warnings=(
            "NO_STRING_MISMATCH_IV_OPTIMIZATION",
            "CURRENT_LIMIT_AT_VMP_IS_APPROXIMATE",
            "COLD_VOC_REQUIRES_DESIGN_TEMPERATURE_SCREENING",
        ),
    )

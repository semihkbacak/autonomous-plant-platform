"""v0.7: research-only bypass-string P-V curve.

Approximate group-level bypass diode behavior.
Does not model shaded cells or parallel-string mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, fsum

import numpy as np
import pvlib

from simulator.solar.pv_array import (
    DeSotoModuleParameters,
)


@dataclass(frozen=True)
class IrradianceGroup:
    module_count: int
    irradiance_w_m2: float
    cell_temp_c: float


@dataclass(frozen=True)
class ShadedStringResult:
    global_mpp_w: float
    global_mpp_v: float
    mppt_window_mpp_w: float
    mppt_window_mpp_v: float
    local_peak_count: int
    limited_by_window: bool
    model: str = (
        "APPROXIMATE_GROUP_BYPASS_NO_PARALLEL_MISMATCH"
    )


def calculate_shaded_string(
    module: DeSotoModuleParameters,
    groups: tuple[IrradianceGroup, ...],
    *,
    mppt_min_v: float,
    mppt_max_v: float,
    bypass_drop_v: float = 0.5,
    steps: int = 800,
) -> ShadedStringResult:

    if (
        not groups
        or type(steps) is not int
        or not 128 <= steps <= 5000
    ):
        raise ValueError(
            "Invalid shading sweep configuration"
        )

    limits = (
        mppt_min_v,
        mppt_max_v,
        bypass_drop_v,
    )

    if not all(isfinite(v) for v in limits):
        raise ValueError(
            "Nonfinite shading limits"
        )

    if not (
        0 < mppt_min_v < mppt_max_v
        and 0 < bypass_drop_v <= 2
    ):
        raise ValueError(
            "Invalid MPPT window/bypass drop"
        )

    diode_points = []

    for group in groups:
        if (
            type(group.module_count) is not int
            or group.module_count < 1
        ):
            raise ValueError(
                "Invalid module count"
            )

        values = (
            group.irradiance_w_m2,
            group.cell_temp_c,
        )

        if not all(isfinite(v) for v in values):
            raise ValueError(
                "Nonfinite shading input"
            )

        if not (
            0 <= group.irradiance_w_m2 <= 1500
            and -60 < group.cell_temp_c < 110
        ):
            raise ValueError(
                "Out-of-range shading input"
            )

        if group.irradiance_w_m2 == 0:
            diode_points.append((
                group.module_count, None
            ))
            continue

        args = pvlib.pvsystem.calcparams_desoto(
            effective_irradiance=group.irradiance_w_m2,
            temp_cell=group.cell_temp_c,
            alpha_sc=module.alpha_sc_a_per_c,
            a_ref=module.a_ref_v,
            I_L_ref=module.i_l_ref_a,
            I_o_ref=module.i_o_ref_a,
            R_sh_ref=module.r_sh_ref_ohm,
            R_s=module.r_s_ohm,
            EgRef=module.eg_ref_ev,
            dEgdT=module.deg_dt_ev_per_k,
        )

        diode_points.append((
            group.module_count, args
        ))

    iscs = [
        float(
            pvlib.pvsystem.singlediode(*args)["i_sc"]
        )
        for _, args in diode_points
        if args is not None
    ]

    if not iscs:
        return ShadedStringResult(
            0, 0, 0, 0, 0, False
        )

    currents = np.linspace(
        0,
        max(iscs) * 1.08,
        steps,
    )

    voltage = np.zeros_like(currents)

    for modules, args in diode_points:

        if args is None:
            voltage -= modules * bypass_drop_v
            continue

        v = np.asarray(
            pvlib.pvsystem.v_from_i(
                currents, *args
            ),
            dtype=float,
        )

        voltage += (
            modules
            * np.maximum(v, -bypass_drop_v)
        )

    voltage = np.maximum(voltage, 0.0)

    power = voltage * currents

    global_idx = int(np.argmax(power))

    in_window = (
        (voltage >= mppt_min_v)
        & (voltage <= mppt_max_v)
    )

    if np.any(in_window):
        indices = np.flatnonzero(in_window)

        idx = indices[
            int(np.argmax(power[in_window]))
        ]

        window_power = float(power[idx])
        window_voltage = float(voltage[idx])
    else:
        window_power = 0.0
        window_voltage = 0.0

    local_peaks = int(sum(
        power[k] > power[k - 1]
        and power[k] >= power[k + 1]
        for k in range(1, len(power) - 1)
    ))

    return ShadedStringResult(
        global_mpp_w=float(power[global_idx]),
        global_mpp_v=float(voltage[global_idx]),
        mppt_window_mpp_w=window_power,
        mppt_window_mpp_v=window_voltage,
        local_peak_count=local_peaks,
        limited_by_window=(
            window_power
            < float(power[global_idx]) - 1e-6
        ),
    )


def apply_shading_to_mppt(
    baseline,
    arrays,
    limits,
    profiles: dict[
        int, tuple[IrradianceGroup, ...]
    ],
):
    """Apply optional shading to one-string MPPT channels.

    Profiles contain explicitly supplied irradiance values.
    Parallel-string mismatch is intentionally unsupported.
    """
    from simulator.solar.multi_mppt_physics import (
        MultiMPPTResult,
    )

    by_channel = {
        item.channel: item
        for item in arrays
    }

    if not set(profiles) <= set(by_channel):
        raise ValueError(
            "Shadow profile references unknown MPPT channel"
        )

    output = []

    for original in baseline.channels:

        profile = profiles.get(original.channel)

        if profile is None:
            output.append(original)
            continue

        config = by_channel[
            original.channel
        ].array

        if config.parallel_strings != 1:
            raise ValueError(
                "Parallel shaded strings unsupported without mismatch solver"
            )

        if sum(
            group.module_count
            for group in profile
        ) != config.modules_per_string:
            raise ValueError(
                "Shading group module counts do not match the string"
            )

        shading = calculate_shaded_string(
            config.module,
            profile,
            mppt_min_v=limits.min_v,
            mppt_max_v=limits.max_v,
        )

        voc = 0.0
        isc = 0.0

        for group in profile:

            if group.irradiance_w_m2 == 0:
                continue

            params = (
                pvlib.pvsystem.calcparams_desoto(
                    effective_irradiance=group.irradiance_w_m2,
                    temp_cell=group.cell_temp_c,
                    alpha_sc=config.module.alpha_sc_a_per_c,
                    a_ref=config.module.a_ref_v,
                    I_L_ref=config.module.i_l_ref_a,
                    I_o_ref=config.module.i_o_ref_a,
                    R_sh_ref=config.module.r_sh_ref_ohm,
                    R_s=config.module.r_s_ohm,
                )
            )

            curve = pvlib.pvsystem.singlediode(
                *params
            )

            voc += (
                group.module_count
                * float(curve["v_oc"])
            )

            isc = max(
                isc,
                float(curve["i_sc"]),
            )

        offered = (
            shading.global_mpp_w / 1000.0
        )

        selected = (
            shading.mppt_window_mpp_w / 1000.0
        )

        voltage = (
            shading.mppt_window_mpp_v
            if selected > 0
            else shading.global_mpp_v
        )

        reasons = [
            "APPROXIMATE_GROUP_BYPASS_PROFILE"
        ]

        if voc > limits.max_dc_v:
            selected = 0.0
            reasons.append(
                "DC_VOC_EXCEEDS_ABSOLUTE_LIMIT"
            )

        if isc > limits.max_short_circuit_a:
            selected = 0.0
            reasons.append(
                "MPPT_SHORT_CIRCUIT_CURRENT_LIMIT"
            )

        if shading.limited_by_window:
            reasons.append(
                "SHADING_MPPT_WINDOW_LOSS_ESTIMATE"
            )

        if selected == 0 and offered > 0:
            reasons.append(
                "SHADING_OUTSIDE_MPPT_WINDOW"
            )

        accepted = min(
            selected,
            voltage
            * limits.max_operating_a
            / 1000.0,
        )

        if accepted < selected - 1e-9:
            reasons.append(
                "MPPT_OPERATING_CURRENT_LIMIT_ESTIMATE"
            )

        current = (
            accepted * 1000.0 / voltage
            if voltage > 0
            else 0.0
        )

        dc = replace(
            original.dc,
            array_pmp_kw=offered,
            array_vmp_v=voltage,
            array_imp_a=current,
            model="APPROXIMATE_GROUP_BYPASS",
            source_quality_flags=tuple(
                dict.fromkeys((
                    *original.dc.source_quality_flags,
                    "SHADING_USER_SUPPLIED_GROUPS_NOT_SITE_VALIDATED",
                ))
            ),
        )

        output.append(
            replace(
                original,
                voltage_v=voltage,
                current_a=current,
                open_circuit_v=voc,
                short_circuit_a=isc,
                offered_kw=offered,
                accepted_kw=accepted,
                rejected_kw=max(
                    0.0,
                    offered - accepted,
                ),
                reasons=tuple(reasons),
                dc=dc,
            )
        )

    offered_total = fsum(
        x.offered_kw for x in output
    )
    accepted_total = fsum(
        x.accepted_kw for x in output
    )

    return MultiMPPTResult(
        channels=tuple(output),
        dc_offered_kw=offered_total,
        dc_accepted_kw=accepted_total,
        dc_rejected_kw=max(
            0.0,
            offered_total - accepted_total,
        ),
        warnings=tuple(
            dict.fromkeys((
                *baseline.warnings,
                "OPT_IN_SHADING_MODEL_NOT_FIELD_VALIDATED",
            ))
        ),
    )
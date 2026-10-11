"""PV array DC model: De Soto five parameters + single-diode MPP.

No inverter, grid, MPPT control loop, shading geometry, spectral or AOI
correction is implemented here. The optical transmission factor is a
simplified aggregate effective-irradiance factor, not a detailed shadow model.

Model parameter values below are synthetic examples, NOT manufacturer data.
To use equipment-specific values, obtain matched De Soto parameters from
an authorized module dataset / manufacturer model and verify them against
reference curves; a datasheet's rated power alone is insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pvlib

from simulator.solar.solar_temperature import (
    FaimanParameters,
    PVTemperature,
    calculate_pv_temperature,
)


@dataclass(frozen=True)
class DeSotoModuleParameters:
    # Reference module (not cell) parameters, at 1000 W/m², 25 °C.
    alpha_sc_a_per_c: float
    a_ref_v: float
    i_l_ref_a: float
    i_o_ref_a: float
    r_sh_ref_ohm: float
    r_s_ohm: float
    eg_ref_ev: float = 1.121
    deg_dt_ev_per_k: float = -0.0002677


@dataclass(frozen=True)
class PVArrayConfiguration:
    modules_per_string: int
    parallel_strings: int
    module: DeSotoModuleParameters
    optical_transmission_factor: float = 1.0


@dataclass(frozen=True)
class PVArrayDCResult:
    poa_global_w_m2: float
    effective_irradiance_w_m2: float
    temperature: PVTemperature
    module_isc_a: float
    module_voc_v: float
    module_imp_a: float
    module_vmp_v: float
    module_pmp_w: float
    array_vmp_v: float
    array_imp_a: float
    array_pmp_kw: float
    source_type: str
    source_quality_flags: tuple[str, ...]
    model: str = "desoto+singlediode"


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _positive(value: float, name: str) -> float:
    v = _finite(value, name)
    if v <= 0:
        raise ValueError(f"{name} must be positive")
    return v


def _validate_config(config: PVArrayConfiguration) -> DeSotoModuleParameters:
    if not isinstance(config.modules_per_string, int) or isinstance(config.modules_per_string, bool) or config.modules_per_string < 1:
        raise ValueError("modules_per_string must be a positive integer")
    if not isinstance(config.parallel_strings, int) or isinstance(config.parallel_strings, bool) or config.parallel_strings < 1:
        raise ValueError("parallel_strings must be a positive integer")
    factor = _finite(config.optical_transmission_factor, "optical_transmission_factor")
    if not 0.0 <= factor <= 1.0:
        raise ValueError("optical_transmission_factor must be in [0,1]")
    m = config.module
    _finite(m.alpha_sc_a_per_c, "alpha_sc_a_per_c")
    _positive(m.a_ref_v, "a_ref_v")
    _positive(m.i_l_ref_a, "i_l_ref_a")
    _positive(m.i_o_ref_a, "i_o_ref_a")
    _positive(m.r_sh_ref_ohm, "r_sh_ref_ohm")
    r_s = _finite(m.r_s_ohm, "r_s_ohm")
    if r_s < 0:
        raise ValueError("r_s_ohm cannot be negative")
    _positive(m.eg_ref_ev, "eg_ref_ev")
    _finite(m.deg_dt_ev_per_k, "deg_dt_ev_per_k")
    return m


def calculate_pv_array_dc(
    poa_global_w_m2: float,
    ambient_temperature_c: float,
    wind_speed_m_s: float,
    config: PVArrayConfiguration,
    temperature_params: FaimanParameters | None = None,
    source_type: str = "DIRECT_POA_INPUT",
    source_quality_flags: tuple[str, ...] = (),
) -> PVArrayDCResult:
    """Calculate DC maximum power for identical series/parallel PV modules.

    This returns DC available maximum-power-point estimates, not AC power.
    It does not command an inverter or guarantee the estimated power is
    achievable under all electrical/topological/thermal constraints.
    """
    m = _validate_config(config)
    poa = _finite(poa_global_w_m2, "poa_global_w_m2")
    if poa < 0:
        raise ValueError("poa_global_w_m2 cannot be negative")
    temp = calculate_pv_temperature(
        poa_global_w_m2=poa,
        ambient_temperature_c=ambient_temperature_c,
        wind_speed_m_s=wind_speed_m_s,
        params=temperature_params,
    )
    effective = poa * config.optical_transmission_factor
    if effective == 0.0:
        return PVArrayDCResult(
            poa_global_w_m2=poa,
            effective_irradiance_w_m2=0.0,
            temperature=temp,
            module_isc_a=0.0,
            module_voc_v=0.0,
            module_imp_a=0.0,
            module_vmp_v=0.0,
            module_pmp_w=0.0,
            array_vmp_v=0.0,
            array_imp_a=0.0,
            array_pmp_kw=0.0,
            source_type=source_type,
            source_quality_flags=source_quality_flags,
        )

    photocurrent, saturation_current, r_s, r_sh, nnsvth = pvlib.pvsystem.calcparams_desoto(
        effective_irradiance=effective,
        temp_cell=temp.cell_temperature_c,
        alpha_sc=m.alpha_sc_a_per_c,
        a_ref=m.a_ref_v,
        I_L_ref=m.i_l_ref_a,
        I_o_ref=m.i_o_ref_a,
        R_sh_ref=m.r_sh_ref_ohm,
        R_s=m.r_s_ohm,
        EgRef=m.eg_ref_ev,
        dEgdT=m.deg_dt_ev_per_k,
    )
    curve = pvlib.pvsystem.singlediode(
        photocurrent=photocurrent,
        saturation_current=saturation_current,
        resistance_series=r_s,
        resistance_shunt=r_sh,
        nNsVth=nnsvth,
        method="lambertw",
    )
    def point(key: str) -> float:
        value = float(curve[key])
        if not isfinite(value) or value < -1.0e-6:
            raise ValueError(f"De Soto model generated invalid {key}")
        return max(0.0, value)

    isc = point("i_sc")
    voc = point("v_oc")
    imp = point("i_mp")
    vmp = point("v_mp")
    pmp = point("p_mp")
    array_vmp = vmp * config.modules_per_string
    array_imp = imp * config.parallel_strings
    array_pmp_kw = pmp * config.modules_per_string * config.parallel_strings / 1000.0
    return PVArrayDCResult(
        poa_global_w_m2=poa,
        effective_irradiance_w_m2=effective,
        temperature=temp,
        module_isc_a=isc,
        module_voc_v=voc,
        module_imp_a=imp,
        module_vmp_v=vmp,
        module_pmp_w=pmp,
        array_vmp_v=array_vmp,
        array_imp_a=array_imp,
        array_pmp_kw=array_pmp_kw,
        source_type=source_type,
        source_quality_flags=source_quality_flags,
    )


def calculate_pv_array_from_poa(
    poa_result: "POAResult",
    ambient_temperature_c: float,
    wind_speed_m_s: float,
    config: PVArrayConfiguration,
    temperature_params: FaimanParameters | None = None,
) -> PVArrayDCResult:
    """Feed previous GHI/DNI/DHI -> POA layer into the DC array model."""
    from simulator.solar.solar_resource import POAResult

    if not isinstance(poa_result, POAResult):
        raise TypeError("poa_result must be a POAResult")
    return calculate_pv_array_dc(
        poa_global_w_m2=poa_result.poa_global_w_m2,
        ambient_temperature_c=ambient_temperature_c,
        wind_speed_m_s=wind_speed_m_s,
        config=config,
        temperature_params=temperature_params,
        source_type=poa_result.source_type,
        source_quality_flags=poa_result.quality_flags,
    )


def synthetic_demo_module() -> DeSotoModuleParameters:
    """Synthetic De Soto values solely for tests / local demonstration.

    DO NOT represent these values as a real panel, datasheet or calibrated
    model. Real deployment requires documented reference parameters.
    """
    return DeSotoModuleParameters(
        alpha_sc_a_per_c=0.005,
        a_ref_v=2.0,
        i_l_ref_a=13.5,
        i_o_ref_a=1e-10,
        r_sh_ref_ohm=400.0,
        r_s_ohm=0.30,
    )


"""
OEM model readiness and temperature approximation.

Unknown OEM parameters remain unknown.
No parameter is inferred from a maximum efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from simulator.solar.component_catalog import Component
from simulator.solar.multi_mppt_physics import MPPTLimits


DESOTO_FIELDS = (
    "alpha_sc_a_per_c",
    "a_ref_v",
    "i_l_ref_a",
    "i_o_ref_a",
    "r_sh_ref_ohm",
    "r_s_ohm",
)

# Declared provenance screening only.
# Does not independently verify manufacturer calibration.
UNTRUSTED_PROVENANCE_MARKERS = (
    "synthetic",
    "fixture",
    "mock",
    "demo",
    "example",
    "placeholder",
    "assumed",
    "estimate",
    "unverified",
    "unknown",
    "not_published",
    "not_extracted",
)

MODEL_FIT_FIELDS = frozenset({
    "a_ref_v",
    "i_l_ref_a",
    "i_o_ref_a",
    "r_sh_ref_ohm",
    "r_s_ohm",
    "eta_nominal_curve_parameter",
})

MODEL_EVIDENCE_MARKERS = (
    "calibrat",
    "validat",
    "verif",
    "model_fit",
    "oem_model",
    "manufacturer_model",
    "desoto_fit",
    "curve_fit",
)


def _has_model_provenance(
    component: Component,
    name: str,
) -> bool:

    record = component.parameters.get(name)

    if record is None:
        return False

    source = record.source_id.strip().lower()
    evidence = record.evidence.strip().lower()

    if not source or not evidence:
        return False

    provenance = f"{source} {evidence}"

    if any(
        marker in provenance
        for marker in UNTRUSTED_PROVENANCE_MARKERS
    ):
        return False

    if name in MODEL_FIT_FIELDS:
        return any(
            marker in evidence
            for marker in MODEL_EVIDENCE_MARKERS
        )

    return True


@dataclass(frozen=True)
class OEMReadiness:
    panel_id: str
    inverter_id: str

    missing: tuple[str, ...]
    warnings: tuple[str, ...]
    unverified: tuple[str, ...] = ()

    @property
    def real_physics_ready(self) -> bool:
        return not self.missing and not self.unverified


def assess_oem_readiness(
    panel: Component,
    inverter: Component,
) -> OEMReadiness:

    if (
        panel.component_type != "panel"
        or inverter.component_type != "inverter"
    ):
        raise ValueError(
            "Panel/inverter component types required"
        )

    required_inverter = (
        "rated_ac_w",
        "eta_nominal_curve_parameter",
    )

    required = (
        ("PANEL", panel, DESOTO_FIELDS),
        ("INVERTER", inverter, required_inverter),
    )

    missing: list[str] = []
    unverified: list[str] = []

    for prefix, component, fields in required:

        for name in fields:

            label = f"{prefix}:{name}"

            if component.number(
                name,
                required=False,
            ) is None:
                missing.append(label)

            elif not _has_model_provenance(
                component,
                name,
            ):
                unverified.append(label)

    warnings = [
        "MPPT_CURVE_AND_TEMPERATURE_DERATING_REQUIRE_OEM_VALIDATION",
        "OEM_DATASHEET_VALUES_NOT_CALIBRATED_IV_MODEL",
    ]

    if unverified:
        warnings.append(
            "UNVERIFIED_OR_SYNTHETIC_MODEL_PROVENANCE"
        )

    return OEMReadiness(
        panel_id=panel.component_id,
        inverter_id=inverter.component_id,
        missing=tuple(missing),
        warnings=tuple(warnings),
        unverified=tuple(unverified),
    )


def require_real_oem_model(
    panel: Component,
    inverter: Component,
) -> None:

    report = assess_oem_readiness(
        panel,
        inverter,
    )

    if not report.real_physics_ready:
        raise ValueError(
            "Missing OEM model coefficients or unverified provenance: "
            + ", ".join(
                (*report.missing, *report.unverified)
            )
        )


def limits_from_oem_catalog(
    inverter: Component,
) -> MPPTLimits:
    """
    Read known per-MPPT electrical limits
    without claiming a calibrated inverter model.
    """

    if inverter.component_type != "inverter":
        raise ValueError("Expected inverter")

    mppt_count = inverter.number("mppt_count")
    string_count = inverter.number("strings_per_mppt")

    if (
        mppt_count != int(mppt_count)
        or string_count != int(string_count)
    ):
        raise ValueError("Invalid integer MPPT count")

    return MPPTLimits(
        mppt_count=int(mppt_count),

        min_v=inverter.number("mppt_min_v"),
        max_v=inverter.number("mppt_max_v"),
        max_dc_v=inverter.number("max_dc_v"),

        max_operating_a=inverter.number(
            "max_operating_current_per_mppt_a"
        ),

        max_short_circuit_a=inverter.number(
            "max_short_circuit_current_per_mppt_a"
        ),

        max_strings=int(string_count),
    )


@dataclass(frozen=True)
class TemperatureEstimate:
    cell_temperature_c: float
    approx_stc_power_w: float
    warnings: tuple[str, ...]


def approximate_oem_panel_temperature(
    panel: Component,
    *,
    irradiance_w_m2: float,
    ambient_c: float,
    wind_m_s: float,
    u0: float | None = None,
    u1: float | None = None,
) -> TemperatureEstimate:
    """
    Faiman-style cell temperature estimate
    and first-order STC-gamma power scaling.

    This does NOT replace De Soto.
    It does NOT compute an OEM inverter AC curve.

    u0/u1 must be explicitly supplied.
    """

    values = (
        irradiance_w_m2,
        ambient_c,
        wind_m_s,
    )

    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        for value in values
    ):
        raise ValueError("Invalid weather input")

    if (
        irradiance_w_m2 < 0
        or wind_m_s < 0
        or ambient_c <= -273.15
    ):
        raise ValueError("Invalid weather range")

    if u0 is None or u1 is None:
        raise ValueError(
            "Explicit Faiman coefficients required; "
            "OEM coefficients not available"
        )

    if (
        not all(isfinite(x) for x in (u0, u1))
        or u0 <= 0
        or u1 < 0
    ):
        raise ValueError("Invalid Faiman coefficients")

    cell_temperature = (
        ambient_c
        + irradiance_w_m2
        / (u0 + u1 * wind_m_s)
    )

    gamma = panel.number("gamma_p_per_C")
    p_stc = panel.number("p_stc_w")

    if p_stc <= 0 or gamma >= 0:
        raise ValueError("Invalid panel STC/gamma")

    power_w = max(
        0.0,
        p_stc
        * irradiance_w_m2 / 1000.0
        * (
            1
            + gamma * (cell_temperature - 25)
        ),
    )

    return TemperatureEstimate(
        cell_temperature_c=cell_temperature,
        approx_stc_power_w=power_w,
        warnings=(
            "APPROXIMATE_STC_GAMMA_MODEL_NOT_DESOTO",
            "FAIMAN_COEFFICIENTS_REQUIRE_SITE_CALIBRATION",
            "DO_NOT_USE_AS_OEM_INVERTER_AC_POWER",
        ),
    )

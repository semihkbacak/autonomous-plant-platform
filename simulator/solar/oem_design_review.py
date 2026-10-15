
"""OEM-reference preliminary PV / MPPT / AC screening. No equipment control."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from simulator.solar.ac_power_limits import (
    ACOperatingRequest,
    ACPowerScreeningResult,
    evaluate_ac_power,
)
from simulator.solar.component_catalog import (
    Component,
    check_mppt_at_stc,
    check_string_temperature_voltage,
)


@dataclass(frozen=True)
class MPPTAssignment:
    mppt_number: int
    panel_id: str
    modules_per_string: int
    strings_per_mppt: int


@dataclass(frozen=True)
class MPPTReview:
    mppt_number: int
    panel_id: str
    string_vmp_stc_v: float
    string_voc_cold_v: float
    operating_current_stc_a: float
    short_circuit_current_stc_a: float
    connected_stc_kw: float
    issues: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class OEMDesignReview:
    inverter_id: str
    channels: tuple[MPPTReview, ...]
    total_connected_stc_kw: float
    max_generator_stc_kw: float | None
    rated_active_kw: float | None
    max_apparent_kva: float
    ac_screen: ACPowerScreeningResult | None
    issues: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passes_preliminary_checks(self) -> bool:
        return not self.issues

    @property
    def approved_for_installation(self) -> bool:
        # This tool cannot perform electrical design approval.
        return False


def _positive_integer(name: str, value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _temperature(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < -273.15
    ):
        raise ValueError(f"Invalid {name}")
    return float(value)


def _sungrow_thermal_anchor(
    inverter_id: str,
    ambient_temperature_c: float | None,
) -> tuple[float | None, str | None, str | None]:
    """Known reference points only; NO interpolation/extrapolation."""

    if inverter_id != "SUNGROW_SG110CX_V152":
        return None, None, "THERMAL_CURVE_NOT_AVAILABLE"

    if ambient_temperature_c == 45.0:
        return (
            110.0,
            "BATIN_REFERENCE_SUNGROW_45C_110KVA",
            None,
        )

    if ambient_temperature_c == 50.0:
        return (
            100.0,
            "BATIN_REFERENCE_SUNGROW_50C_100KVA",
            None,
        )

    return None, None, "THERMAL_CURVE_NOT_AVAILABLE"


def review_oem_design(
    catalog: Mapping[str, Component],
    *,
    inverter_id: str,
    assignments: Sequence[MPPTAssignment],
    min_cell_temperature_c: float,
    max_cell_temperature_c: float,
    ambient_temperature_c: float | None = None,
    requested_active_kw: float | None = None,
    requested_reactive_kvar: float | None = None,
) -> OEMDesignReview:
    """
    Screen a proposed PV configuration against OEM reference limits.

    This is NOT a dynamic multi-MPPT simulation
    and NOT an installation approval.
    """

    if inverter_id not in catalog:
        raise ValueError("Inverter not found in catalog")

    inverter = catalog[inverter_id]

    if inverter.component_type != "inverter":
        raise ValueError("Expected inverter catalog component")

    cold = _temperature(
        "minimum cell temperature",
        min_cell_temperature_c,
    )
    hot = _temperature(
        "maximum cell temperature",
        max_cell_temperature_c,
    )

    if cold > hot:
        raise ValueError(
            "Minimum cell temperature exceeds maximum"
        )

    ambient = (
        None
        if ambient_temperature_c is None
        else _temperature(
            "ambient temperature",
            ambient_temperature_c,
        )
    )

    if (
        (requested_active_kw is None)
        != (requested_reactive_kvar is None)
    ):
        raise ValueError(
            "Both active and reactive power requests are required"
        )

    if not assignments:
        raise ValueError(
            "At least one MPPT assignment is required"
        )

    max_mppts = inverter.number("mppt_count")

    if max_mppts != int(max_mppts) or max_mppts <= 0:
        raise ValueError("Invalid OEM MPPT count")

    max_mppts = int(max_mppts)

    seen: set[int] = set()
    channels: list[MPPTReview] = []

    issues: list[str] = []

    warnings: list[str] = [
        "SCREENING_ONLY_NOT_INSTALLATION_APPROVAL",
        "DYNAMIC_MULTI_MPPT_PHYSICS_NOT_IMPLEMENTED",
    ]

    total_stc_kw = 0.0

    # --------------------------------------------------------
    # CHECK EACH MPPT CHANNEL
    # --------------------------------------------------------

    for a in assignments:
        if not isinstance(a, MPPTAssignment):
            raise ValueError("Expected MPPTAssignment")

        mppt = _positive_integer(
            "mppt_number",
            a.mppt_number,
        )

        if mppt > max_mppts:
            raise ValueError(
                "MPPT index exceeds inverter MPPT count"
            )

        if mppt in seen:
            raise ValueError("Duplicate MPPT assignment")

        seen.add(mppt)

        modules = _positive_integer(
            "modules_per_string",
            a.modules_per_string,
        )

        strings = _positive_integer(
            "strings_per_mppt",
            a.strings_per_mppt,
        )

        if a.panel_id not in catalog:
            raise ValueError(
                f"Panel not found: {a.panel_id}"
            )

        panel = catalog[a.panel_id]

        if panel.component_type != "panel":
            raise ValueError(
                f"Expected panel: {a.panel_id}"
            )

        stc = check_mppt_at_stc(
            panel,
            inverter,
            modules,
            strings,
        )

        temperature = check_string_temperature_voltage(
            panel,
            inverter,
            modules,
            cold,
            hot,
        )

        stc_kw = (
            panel.number("p_stc_w")
            * modules
            * strings
            / 1000.0
        )

        total_stc_kw += stc_kw

        channel_issues = tuple(
            dict.fromkeys(
                (*stc.issues, *temperature.issues)
            )
        )

        channel_warnings = tuple(
            dict.fromkeys(
                temperature.warnings
            )
        )

        channels.append(
            MPPTReview(
                mppt_number=mppt,
                panel_id=a.panel_id,
                string_vmp_stc_v=stc.string_vmp_v,
                string_voc_cold_v=(
                    temperature.cold_string_voc_v
                ),
                operating_current_stc_a=stc.mppt_imp_a,
                short_circuit_current_stc_a=stc.mppt_isc_a,
                connected_stc_kw=stc_kw,
                issues=channel_issues,
                warnings=channel_warnings,
            )
        )

        issues.extend(
            f"MPPT_{mppt}:{code}"
            for code in channel_issues
        )

        warnings.extend(
            f"MPPT_{mppt}:{code}"
            for code in channel_warnings
        )

    # --------------------------------------------------------
    # TOTAL PV GENERATOR STC LIMIT
    # --------------------------------------------------------

    generator_w = inverter.number(
        "max_generator_stc_w",
        required=False,
    )

    generator_kw = (
        generator_w / 1000.0
        if generator_w is not None
        else None
    )

    if generator_kw is None:
        warnings.append(
            "MAX_GENERATOR_STC_RATING_UNAVAILABLE"
        )
    elif total_stc_kw > generator_kw + 1e-9:
        issues.append(
            "TOTAL_PV_STC_EXCEEDS_GENERATOR_LIMIT"
        )

    # --------------------------------------------------------
    # AC ACTIVE AND APPARENT POWER
    # --------------------------------------------------------

    rated_w = inverter.number(
        "rated_ac_w",
        required=False,
    )

    rated_kw = (
        rated_w / 1000.0
        if rated_w is not None
        else None
    )

    if rated_kw is None:
        warnings.append(
            "RATED_ACTIVE_POWER_UNAVAILABLE"
        )

    nominal_eta = inverter.number(
        "eta_nominal_curve_parameter",
        required=False,
    )

    if nominal_eta is None:
        warnings.append(
            "OEM_NOMINAL_EFFICIENCY_NOT_VERIFIED"
        )

    kva = (
        inverter.number("max_ac_apparent_va")
        / 1000.0
    )

    if kva <= 0:
        raise ValueError(
            "Invalid OEM apparent-power rating"
        )

    temp_limit, temp_source, temp_warning = (
        _sungrow_thermal_anchor(
            inverter_id,
            ambient,
        )
    )

    if temp_warning:
        warnings.append(temp_warning)

    if ambient is None:
        warnings.append(
            "OPERATING_AMBIENT_TEMPERATURE_NOT_SPECIFIED"
        )

    ac_result = None

    if requested_active_kw is not None:
        ac_result = evaluate_ac_power(
            ACOperatingRequest(
                nameplate_kva=kva,
                requested_active_kw=requested_active_kw,
                requested_reactive_kvar=(
                    requested_reactive_kvar
                ),
                temperature_limit_kva=temp_limit,
                temperature_limit_source=temp_source,
            )
        )

        if ac_result.status != "WITHIN_CAPABILITY":
            issues.append(
                "AC_REQUEST_OUTSIDE_SIMPLIFIED_PQ_LIMIT"
            )

        if (
            rated_kw is not None
            and requested_active_kw > rated_kw + 1e-9
        ):
            issues.append(
                "REQUEST_EXCEEDS_RATED_ACTIVE_POWER"
            )

        warnings.extend(ac_result.warnings)

    return OEMDesignReview(
        inverter_id=inverter_id,
        channels=tuple(channels),
        total_connected_stc_kw=total_stc_kw,
        max_generator_stc_kw=generator_kw,
        rated_active_kw=rated_kw,
        max_apparent_kva=kva,
        ac_screen=ac_result,
        issues=tuple(dict.fromkeys(issues)),
        warnings=tuple(dict.fromkeys(warnings)),
    )

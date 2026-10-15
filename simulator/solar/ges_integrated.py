
"""GES v0.4: independent MPPT DC inputs -> one AC inverter -> P/Q dispatch.

Synthetic, simulation-only. Distinct MPPT voltages are NEVER summed or
represented as a fictitious single DC voltage.
"""
from __future__ import annotations
from simulator.solar.ges_v07_inverter import (
    InverterScreeningCurve,
)

from simulator.solar.ges_v07_shading import (
    IrradianceGroup,
    apply_shading_to_mppt,
)
from dataclasses import dataclass, replace
from math import fsum, isfinite
from typing import Mapping, Sequence

from pvlib.inverter import pvwatts

from simulator.solar.ac_power_limits import ACOperatingRequest, evaluate_ac_power
from simulator.solar.inverter import InverterConfig, InverterResult
from simulator.solar.multi_mppt_physics import (
    MPPTArray, MPPTLimits, MultiMPPTResult, calculate_multi_mppt_dc,
)
from simulator.solar.pq_dispatch import PQCapability
from simulator.solar.solar_pipeline import (
    SolarArrayReport, SolarAsset, SolarPhysicsPipeline,
    SolarPipelineReport, SolarWeather,
)
from simulator.solar.solar_plant import SolarPlantReport
from simulator.solar.solar_resource import SolarSite


@dataclass(frozen=True)
class InverterMPPTConfig:
    channels: tuple[MPPTArray, ...]
    limits: MPPTLimits


@dataclass(frozen=True)
class InverterMPPTReport:
    inverter_id: str
    dc: MultiMPPTResult


@dataclass(frozen=True)
class InverterPQScreen:
    inverter_id: str
    requested_reactive_kvar: float
    applied_kva_limit: float
    active_limit_kw: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class IntegratedSolarReport(SolarPipelineReport):
    mppt_reports: tuple[InverterMPPTReport, ...] = ()
    pq_reports: tuple[InverterPQScreen, ...] = ()


def _power(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"Invalid {name}")
    return float(value)


def _baseline_inverter(
    config: InverterConfig,
    mppt: MultiMPPTResult,
    *,
    grid_available: bool,
    emergency_stop: bool,
    fault_active: bool,
    maintenance_lock: bool,
) -> InverterResult:
    """
    Convert the sum of accepted MPPT DC powers once,
    without constructing a fictitious DC voltage.
    """
    offered = mppt.dc_offered_kw
    accepted = mppt.dc_accepted_kw

    reasons = [
        f"MPPT_{ch.channel}:{reason}"
        for ch in mppt.channels
        for reason in ch.reasons
    ]

    blockers = []

    if not grid_available:
        blockers.append("GRID_UNAVAILABLE")

    if emergency_stop:
        blockers.append("PLANT_EMERGENCY_STOP")

    if fault_active:
        blockers.append("INVERTER_FAULT")

    if maintenance_lock:
        blockers.append("MAINTENANCE_LOCK")

    if blockers:
        return InverterResult(
            config.inverter_id, "BLOCKED", offered, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            tuple(dict.fromkeys((*reasons, *blockers))),
        )

    if accepted <= 0.0:
        return InverterResult(
            config.inverter_id, "IDLE", offered, 0.0,
            0.0, 0.0, 0.0, offered, 0.0, 0.0, 0.0,
            tuple(dict.fromkeys((*reasons, "NO_ACCEPTED_DC_POWER"))),
        )

    # Exactly one DC -> AC conversion per inverter.
    pdc0_kw = config.rated_ac_kw / config.nominal_efficiency

    available = max(
        0.0,
        float(
            pvwatts(
                pdc=accepted,
                pdc0=pdc0_kw,
                eta_inv_nom=config.nominal_efficiency,
            )
        ),
    )

    zeta = accepted / pdc0_kw

    eta = (config.nominal_efficiency / 0.9637) * (
        -0.0162 * zeta
        - 0.0059 / zeta
        + 0.9858
    )

    unclipped = min(
        accepted,
        max(0.0, accepted * eta),
    )

    available = min(available, unclipped)

    rejected = max(0.0, offered - accepted)
    clipping = max(0.0, unclipped - available)

    if rejected > 1e-9:
        reasons.append("MPPT_DC_REJECTED")

    if clipping > 1e-9:
        reasons.append("AC_CLIPPING")

    return InverterResult(
        config.inverter_id,
        "RUNNING" if available > 0 else "CURTAILED",
        offered,
        accepted,
        unclipped,
        available,
        available,
        rejected,
        max(0.0, accepted - unclipped),
        clipping,
        0.0,
        tuple(dict.fromkeys(reasons)),
    )


class IntegratedSolarPhysicsPipeline(SolarPhysicsPipeline):
    """
    Opt-in GES v0.4 simulation path.

    Existing SolarPhysicsPipeline remains available
    for legacy tests and scenarios.
    """

    def __init__(
        self,
        site: SolarSite,
        assets: Sequence[SolarAsset],
        mppt_configs: Mapping[str, InverterMPPTConfig],
        *,
        inverter_curves: Mapping[str, InverterScreeningCurve] | None = None,
        shading_profiles: Mapping[
            str, Mapping[int, tuple[IrradianceGroup, ...]]
        ] | None = None,
    ) -> None:
        super().__init__(site, assets)

        self.inverter_curves = dict(inverter_curves or {})
        self.shading_profiles = {
            key: dict(value)
            for key, value in (shading_profiles or {}).items()
        }

        if not set(self.inverter_curves) <= self.inverter_ids:
            raise ValueError("Unknown inverter curve ID")

        if not set(self.shading_profiles) <= self.inverter_ids:
            raise ValueError("Unknown shaded inverter ID")

        for asset in self.assets:
            curve = self.inverter_curves.get(asset.inverter.inverter_id)
            if curve is not None and (
                curve.inverter_id != asset.inverter.inverter_id
                or curve.ac_rating_kw > asset.inverter.rated_ac_kw
            ):
                raise ValueError("Inverter screening curve/nameplate mismatch")

        if set(mppt_configs) != self.inverter_ids:
            raise ValueError("MPPT configuration must cover every inverter")

        self.mppt_configs = dict(mppt_configs)

        for asset in self.assets:
            inverter = asset.inverter
            entry = self.mppt_configs[inverter.inverter_id]

            if not entry.channels:
                raise ValueError("Every inverter needs MPPT channels")

            if (
                entry.limits.min_v < inverter.mppt_min_v
                or entry.limits.max_v > inverter.mppt_max_v
                or entry.limits.max_dc_v > inverter.max_dc_voltage_v
            ):
                raise ValueError("MPPT limits exceed inverter envelope")

    def simulate(
        self,
        weather: SolarWeather,
        requested_target_kw: float | None = None,
        *,
        grid_available: bool = True,
        emergency_stop: bool = False,
        fault_inverter_ids: frozenset[str] = frozenset(),
        maintenance_inverter_ids: frozenset[str] = frozenset(),
        pq_capabilities: Mapping[str, PQCapability] | None = None,
        reactive_requests_kvar: Mapping[str, float] | None = None,
    ) -> IntegratedSolarReport:

        _power("wind speed", weather.wind_speed_m_s)

        if (
            not isfinite(weather.ambient_temperature_c)
            or weather.ambient_temperature_c <= -273.15
        ):
            raise ValueError(
                "Invalid ambient temperature"
            )

        unknown_ids = (
            set(fault_inverter_ids)
            | set(maintenance_inverter_ids)
        ) - self.inverter_ids

        if unknown_ids:
            raise ValueError(
                "Unknown inverter ID"
            )

        if (
            (pq_capabilities is None)
            != (reactive_requests_kvar is None)
        ):
            raise ValueError(
                "Both P-Q mapping and Q requests required"
            )

        if pq_capabilities is not None:
            if (
                set(pq_capabilities) != self.inverter_ids
                or set(reactive_requests_kvar)
                != self.inverter_ids
            ):
                raise ValueError(
                    "P-Q mapping must cover every inverter"
                )

        if requested_target_kw is not None:
            _power("requested target", requested_target_kw)

        reports: list[InverterMPPTReport] = []
        arrays: list[SolarArrayReport] = []
        baseline: list[InverterResult] = []

        pq_caps = {}
        pq_screens: list[InverterPQScreen] = []
        pq_limited = False

        # ----------------------------------------------------
        # PER-INVERTER MPPT CALCULATION AND AC CONVERSION
        # ----------------------------------------------------

        for asset in self.assets:

            config = asset.inverter
            iid = config.inverter_id

            mppt_config = self.mppt_configs[iid]

            mppt = calculate_multi_mppt_dc(
                self.site,
                weather,
                mppt_config.channels,
                mppt_config.limits,
            )

            if iid in self.shading_profiles:
                mppt = apply_shading_to_mppt(
                    mppt,
                    mppt_config.channels,
                    mppt_config.limits,
                    self.shading_profiles[iid],
                )

            reports.append(
                InverterMPPTReport(iid, mppt)
            )

            # Reuse actual POA and De Soto results
            # calculated for each MPPT channel.
            for config_channel, measured in zip(
                mppt_config.channels,
                mppt.channels,
            ):
                if (
                    config_channel.channel != measured.channel
                    or measured.poa is None
                    or measured.dc is None
                ):
                    raise ValueError(
                        "MPPT physics metadata missing or out of order"
                    )

                arrays.append(
                    SolarArrayReport(
                        iid,
                        measured.poa,
                        measured.dc,
                    )
                )

            actual = _baseline_inverter(
                config,
                mppt,
                grid_available=grid_available,
                emergency_stop=emergency_stop,
                fault_active=iid in fault_inverter_ids,
                maintenance_lock=iid in maintenance_inverter_ids,
            )

            curve = self.inverter_curves.get(iid)

            if (
                curve is not None
                and actual.status not in ("BLOCKED", "IDLE")
            ):
                screening = curve.screen(
                    actual.dc_accepted_kw,
                    weather.ambient_temperature_c,
                )

                available = screening["ac_kw"]
                unclipped = max(
                    0.0,
                    actual.dc_accepted_kw
                    - screening["conversion_loss_kw"],
                )

                actual = replace(
                    actual,
                    ac_unclipped_kw=unclipped,
                    ac_available_kw=available,
                    ac_dispatched_kw=available,
                    conversion_loss_kw=screening["conversion_loss_kw"],
                    clipping_loss_kw=screening["clipped_kw"],
                    status="RUNNING" if available > 0 else "CURTAILED",
                    reasons=tuple(dict.fromkeys((
                        *actual.reasons,
                        "USER_SUPPLIED_CURVE_NOT_OEM_CALIBRATED",
                    ))),
                )

            baseline.append(actual)
            cap = actual.ac_available_kw

            # ------------------------------------------------
            # P-Q ACTIVE POWER CAPABILITY SCREEN
            # ------------------------------------------------

            if pq_capabilities is not None:

                capability = pq_capabilities[iid]

                if not isinstance(
                    capability,
                    PQCapability,
                ):
                    raise ValueError(
                        "Expected PQCapability"
                    )

                if capability.rated_active_kw is None:
                    raise ValueError(
                        f"Rated active power unknown: {iid}"
                    )

                _power(
                    "rated active power",
                    capability.rated_active_kw,
                )

                if capability.rated_active_kw <= 0:
                    raise ValueError(
                        "Rated active power must be positive"
                    )

                q = reactive_requests_kvar[iid]

                screen = evaluate_ac_power(
                    ACOperatingRequest(
                        nameplate_kva=capability.nameplate_kva,
                        requested_active_kw=cap,
                        requested_reactive_kvar=q,
                        temperature_limit_kva=(
                            capability.temperature_limit_kva
                        ),
                        temperature_limit_source=(
                            capability.temperature_limit_source
                        ),
                    )
                )

                if screen.max_active_kw is None:
                    raise ValueError(
                        f"Reactive request infeasible: {iid}"
                    )

                cap = min(
                    cap,
                    screen.max_active_kw,
                    capability.rated_active_kw,
                )

                pq_screens.append(
                    InverterPQScreen(
                        iid,
                        float(q),
                        screen.applied_kva_limit,
                        cap,
                        tuple((
                            *screen.warnings,
                            "Q_REQUEST_NOT_MEASURED_OUTPUT",
                        )),
                    )
                )

                if cap < actual.ac_available_kw - 1e-9:
                    pq_limited = True

            pq_caps[iid] = cap

        # ----------------------------------------------------
        # PLANT-WIDE ACTIVE POWER DISTRIBUTION
        # ----------------------------------------------------

        total_cap = fsum(pq_caps.values())

        total_baseline = fsum(
            r.ac_available_kw
            for r in baseline
        )

        target = (
            total_cap
            if requested_target_kw is None
            else min(
                total_cap,
                requested_target_kw,
            )
        )

        dispatched: list[InverterResult] = []

        for item in baseline:

            cap = pq_caps[item.inverter_id]

            power = (
                target * (cap / total_cap)
                if total_cap > 0
                else 0.0
            )

            if item.status in ("BLOCKED", "IDLE"):
                dispatched.append(item)
                continue

            reasons = list(item.reasons)

            if power < item.ac_available_kw - 1e-9:
                reasons.append(
                    "ACTIVE_POWER_LIMIT"
                )

            dispatched.append(
                replace(
                    item,
                    status=(
                        "RUNNING"
                        if power > 0
                        else "CURTAILED"
                    ),
                    ac_dispatched_kw=power,
                    curtailment_kw=max(
                        0.0,
                        item.ac_available_kw - power,
                    ),
                    reasons=tuple(
                        dict.fromkeys(reasons)
                    ),
                )
            )

        # ----------------------------------------------------
        # REBUILD FINAL PLANT REPORT
        # ----------------------------------------------------

        delivered = fsum(
            item.ac_dispatched_kw
            for item in dispatched
        )

        curtailed = fsum(
            item.curtailment_kw
            for item in dispatched
        )

        unserved = (
            0.0
            if requested_target_kw is None
            else max(
                0.0,
                requested_target_kw - delivered,
            )
        )

        reasons = []

        if emergency_stop:
            reasons.append(
                "PLANT_EMERGENCY_STOP"
            )

        if not grid_available:
            reasons.append(
                "GRID_UNAVAILABLE"
            )

        if total_baseline <= 0:
            reasons.append(
                "NO_AC_POWER_AVAILABLE"
            )

        if pq_limited:
            reasons.append(
                "PQ_ACTIVE_POWER_CAP_APPLIED"
            )

        if curtailed > 1e-9:
            reasons.append(
                "CURTAILMENT_APPLIED"
            )

        if unserved > 1e-7:
            reasons.append(
                "INSUFFICIENT_AVAILABLE_POWER"
            )

        plant = SolarPlantReport(
            requested_target_kw=requested_target_kw,
            available_power_kw=total_baseline,
            dispatched_power_kw=delivered,
            curtailed_power_kw=curtailed,
            unserved_target_kw=unserved,
            grid_available=grid_available,
            emergency_stop=emergency_stop,
            inverter_results=tuple(dispatched),
            reasons=tuple(reasons),
        )

        return IntegratedSolarReport(
            timestamp_utc=weather.irradiance.timestamp,
            array_reports=tuple(arrays),
            plant=plant,
            mppt_reports=tuple(reports),
            pq_reports=tuple(pq_screens),
        )
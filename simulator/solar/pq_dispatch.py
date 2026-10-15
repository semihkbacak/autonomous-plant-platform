
"""
Opt-in active/reactive power capability dispatch.

Simulation-only active power limitation.
This does NOT guarantee actual reactive power
delivery or model OEM-specific P-Q curves.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Sequence

from simulator.solar.ac_power_limits import (
    ACOperatingRequest,
    evaluate_ac_power,
)

from simulator.solar.inverter import (
    InverterResult,
    simulate_inverter,
)

from simulator.solar.solar_plant import (
    SolarInverterInput,
    SolarPlantReport,
    SolarPlantSimulator,
)


@dataclass(frozen=True)
class PQCapability:
    nameplate_kva: float

    rated_active_kw: float | None

    temperature_limit_kva: float | None = None

    temperature_limit_source: str | None = None


@dataclass(frozen=True)
class PQPlantResult:
    plant: SolarPlantReport

    screened_reactive_kvar: dict[str, float]

    max_active_kw_by_inverter: dict[str, float]

    warnings: tuple[str, ...]


def dispatch_with_pq(
    plant: SolarPlantSimulator,
    inputs: Sequence[SolarInverterInput],
    *,
    capabilities: Mapping[str, PQCapability],
    reactive_requests_kvar: Mapping[str, float],
    requested_target_kw: float | None = None,
    grid_available: bool = True,
    emergency_stop: bool = False,
) -> PQPlantResult:
    """
    Recalculate active-power dispatch subject to
    a simplified P-Q apparent-power envelope.

    The inverter's physical DC/AC conversion
    continues to use the existing inverter.py.

    This is not a hardware command.
    """

    inverter_ids = tuple(
        config.inverter_id
        for config in plant.inverters
    )

    if (
        set(capabilities) != set(inverter_ids)
        or set(reactive_requests_kvar)
        != set(inverter_ids)
    ):
        raise ValueError(
            "Missing or extra inverter P-Q configuration"
        )

    # 1. Get physical inverter output WITHOUT
    # an active-power dispatch target.
    baseline = plant.simulate(
        inputs,

        requested_target_kw=None,

        grid_available=grid_available,

        emergency_stop=emergency_stop,
    )

    input_by_id = {
        item.inverter_id: item
        for item in inputs
    }

    baseline_by_id = {
        item.inverter_id: item
        for item in baseline.inverter_results
    }

    active_caps = {}
    q_requests = {}
    warnings = []

    # 2. Determine each inverter's independent
    # maximum active power under requested Q.
    for config in plant.inverters:

        inverter_id = config.inverter_id

        capability = capabilities[inverter_id]

        if not isinstance(
            capability,
            PQCapability,
        ):
            raise ValueError(
                "Expected PQCapability"
            )

        q = reactive_requests_kvar[
            inverter_id
        ]

        if (
            isinstance(q, bool)
            or not isinstance(q, (int, float))
            or not isfinite(q)
        ):
            raise ValueError(
                "Invalid reactive request"
            )

        operating_screen = evaluate_ac_power(
            ACOperatingRequest(
                nameplate_kva=(
                    capability.nameplate_kva
                ),

                requested_active_kw=(
                    baseline_by_id[
                        inverter_id
                    ].ac_available_kw
                ),

                requested_reactive_kvar=q,

                temperature_limit_kva=(
                    capability.temperature_limit_kva
                ),

                temperature_limit_source=(
                    capability.temperature_limit_source
                ),
            )
        )

        if operating_screen.max_active_kw is None:
            raise ValueError(
                f"Reactive request infeasible: {inverter_id}"
            )

        rated_active_kw = (
            capability.rated_active_kw
        )

        if rated_active_kw is None:
            raise ValueError(
                f"Rated active power unknown: {inverter_id}"
            )

        if (
            isinstance(rated_active_kw, bool)
            or not isinstance(
                rated_active_kw,
                (int, float),
            )
            or not isfinite(rated_active_kw)
            or rated_active_kw <= 0
        ):
            raise ValueError(
                "Invalid rated active power"
            )

        available = baseline_by_id[
            inverter_id
        ].ac_available_kw

        active_caps[inverter_id] = min(
            available,
            operating_screen.max_active_kw,
            rated_active_kw,
        )

        q_requests[inverter_id] = float(q)

        warnings.extend(
            operating_screen.warnings
        )

        if (
            active_caps[inverter_id]
            < available - 1e-9
        ):
            warnings.append(
                f"PQ_ACTIVE_LIMIT:{inverter_id}"
            )

    # 3. Validate plant target.
    if requested_target_kw is not None:

        if (
            isinstance(requested_target_kw, bool)
            or not isinstance(
                requested_target_kw,
                (int, float),
            )
            or not isfinite(requested_target_kw)
            or requested_target_kw < 0
        ):
            raise ValueError(
                "Invalid requested target"
            )

    total_cap = sum(
        active_caps.values()
    )

    target = (
        total_cap
        if requested_target_kw is None
        else min(
            total_cap,
            requested_target_kw,
        )
    )

    # 4. Proportional active dispatch
    # based on Q-constrained capacities.
    results: list[InverterResult] = []

    for config in plant.inverters:

        inverter_id = config.inverter_id

        baseline_result = baseline_by_id[
            inverter_id
        ]

        if (
            baseline_result.status == "BLOCKED"
            or baseline_result.ac_available_kw <= 0
        ):
            results.append(
                baseline_result
            )
            continue

        share = (
            active_caps[inverter_id] / total_cap
            if total_cap > 0
            else 0.0
        )

        inverter_active_target = (
            target * share
        )

        input_data = input_by_id[
            inverter_id
        ]

        # Re-run the existing physical inverter model
        # with the constrained active-power target.
        constrained_result = simulate_inverter(
            config,

            input_data.dc_power_kw,
            input_data.dc_voltage_v,

            grid_available=grid_available,

            fault_active=input_data.fault_active,

            maintenance_lock=input_data.maintenance_lock,

            active_power_limit_kw=(
                inverter_active_target
            ),
        )

        results.append(
            constrained_result
        )

    # 5. Rebuild plant totals from actual
    # constrained inverter results.
    dispatched_kw = sum(
        result.ac_dispatched_kw
        for result in results
    )

    curtailed_kw = sum(
        result.curtailment_kw
        for result in results
    )

    unserved_kw = (
        0.0
        if requested_target_kw is None
        else max(
            0.0,
            requested_target_kw - dispatched_kw,
        )
    )

    reasons = list(
        baseline.reasons
    )

    if any(
        active_caps[inverter_id]
        < baseline_by_id[
            inverter_id
        ].ac_available_kw - 1e-9
        for inverter_id in inverter_ids
    ):
        reasons.append(
            "PQ_ACTIVE_POWER_CAP_APPLIED"
        )

    if (
        curtailed_kw > 1e-9
        and "CURTAILMENT_APPLIED" not in reasons
    ):
        reasons.append(
            "CURTAILMENT_APPLIED"
        )

    if (
        unserved_kw > 1e-7
        and "INSUFFICIENT_AVAILABLE_POWER"
        not in reasons
    ):
        reasons.append(
            "INSUFFICIENT_AVAILABLE_POWER"
        )

    final_report = SolarPlantReport(
        requested_target_kw=(
            requested_target_kw
        ),

        available_power_kw=(
            baseline.available_power_kw
        ),

        dispatched_power_kw=dispatched_kw,

        curtailed_power_kw=curtailed_kw,

        unserved_target_kw=unserved_kw,

        grid_available=grid_available,

        emergency_stop=emergency_stop,

        inverter_results=tuple(results),

        reasons=tuple(
            dict.fromkeys(reasons)
        ),
    )

    return PQPlantResult(
        plant=final_report,

        screened_reactive_kvar=q_requests,

        max_active_kw_by_inverter=active_caps,

        warnings=tuple(
            dict.fromkeys(warnings)
        ),
    )


"""HES v0.6-v0.9: Deterministic scenarios and synthetic annual screening."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from core.models import PlantState
from simulator.hydro import HydroPlantSimulator
from simulator.hydro_safety_supervisor import HydroSimulationSupervisor
from simulator.hydro_physics import calculate_hydro_power_mw
from simulator.scenarios import ScenarioType


CASES = (
    "BASELINE",
    "DUAL_UNIT",
    "POWER_STEP",
    "GRID_LOSS",
    "GRID_RECOVERY",
    "UNIT_FAULT",
    "HIGH_TEMPERATURE",
    "HIGH_VIBRATION",
    "LOW_HEADPOND",
    "LOW_NET_HEAD",
    "EMERGENCY_STOP",
    "MAINTENANCE_LOCK",
)


def run_dynamic_case(
    case: str,
    *,
    seconds: int = 120,
    sample_every: int = 5,
) -> list[PlantState]:

    if case not in CASES:
        raise ValueError("Unknown HES case")

    if type(seconds) is not int or not 10 <= seconds <= 86400:
        raise ValueError("seconds outside 10..86400")

    if (
        type(sample_every) is not int
        or not 1 <= sample_every <= seconds
    ):
        raise ValueError("Invalid sample_every")

    sim = HydroPlantSimulator()
    sim.set_auto_tick(False)

    supervisor = HydroSimulationSupervisor()

    if case == "DUAL_UNIT":
        assert sim.request_start("UNIT_1").accepted
        assert sim.request_start("UNIT_2").accepted
    else:
        assert sim.request_start("UNIT_1").accepted

    states = [sim.snapshot()]

    event_second = max(6, seconds // 4)
    recovery_second = max(event_second + 1, seconds // 2)

    for second in range(1, seconds + 1):

        if second == event_second:

            if case == "POWER_STEP":
                result = sim.request_power_setpoint(
                    "UNIT_1", 8.0
                )
                if not result.accepted:
                    raise RuntimeError(result.message)

            elif case in ("GRID_LOSS", "GRID_RECOVERY"):
                sim.apply_scenario(
                    ScenarioType.GRID_LOSS,
                    seed=1,
                )

            elif case == "UNIT_FAULT":
                sim.apply_scenario(
                    ScenarioType.UNIT_FAULT,
                    seed=1,
                )

            elif case == "HIGH_TEMPERATURE":
                sim.apply_scenario(
                    ScenarioType.HIGH_TEMPERATURE,
                    seed=1,
                )

            elif case == "HIGH_VIBRATION":
                sim.apply_scenario(
                    ScenarioType.HIGH_VIBRATION,
                    seed=1,
                )

            elif case == "LOW_HEADPOND":
                sim.apply_scenario(
                    ScenarioType.LOW_HEADPOND,
                    seed=1,
                )

            elif case == "LOW_NET_HEAD":
                sim.state.gross_head_m = 75.0

            elif case == "EMERGENCY_STOP":
                sim.set_emergency_stop(True)

            elif case == "MAINTENANCE_LOCK":
                sim.set_maintenance_lock(True)

        if (
            case == "GRID_RECOVERY"
            and second == recovery_second
        ):
            sim.state.grid_available = True

            supervisor.reset(
                sim,
                operator_acknowledged=True,
            )

        result = supervisor.guarded_tick(sim)

        if (
            second % sample_every == 0
            or second == seconds
        ):
            states.append(result)

    return states


@dataclass(frozen=True)
class SteadyStateAnnual:
    days: int
    intervals: int
    energy_mwh: float
    peak_mw: float
    minimum_mw: float
    zero_production_intervals: int

    scope: str = (
        "SYNTHETIC_15MIN_STEADY_STATE_NOT_DYNAMIC_OR_FIELD_VALIDATED"
    )

    def report(self) -> dict:
        return asdict(self)


def annual_steady_state(
    *,
    days: int = 365,
) -> SteadyStateAnnual:

    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError(
            "days must be integer 1..365"
        )

    energy = 0.0
    peak = 0.0
    low = math.inf
    zero = 0

    for i in range(days * 96):

        day = i / 96.0
        hour = (i % 96) / 4.0

        seasonal = math.sin(
            2 * math.pi * day / 365.0
        )

        daily = math.sin(
            2 * math.pi * hour / 24.0
        )

        net_head_m = 285.0 + 12.0 * seasonal

        flow_unit_1 = max(
            0.0,
            2.8 + 0.75 * seasonal + 0.2 * daily,
        )

        flow_unit_2 = max(
            0.0,
            2.5 + 0.65 * seasonal - 0.2 * daily,
        )

        power = sum(
            min(
                15.0,
                calculate_hydro_power_mw(
                    flow,
                    net_head_m,
                    0.90,
                    0.97,
                ),
            )
            for flow in (
                flow_unit_1,
                flow_unit_2,
            )
        )

        if (
            not math.isfinite(power)
            or power < 0
            or power > 30.0 + 1e-8
        ):
            raise ValueError(
                "Invalid hydro annual energy/power result"
            )

        energy += power * 0.25
        peak = max(peak, power)
        low = min(low, power)

        zero += int(power == 0)

    return SteadyStateAnnual(
        days=days,
        intervals=days * 96,
        energy_mwh=energy,
        peak_mw=peak,
        minimum_mw=low,
        zero_production_intervals=zero,
    )

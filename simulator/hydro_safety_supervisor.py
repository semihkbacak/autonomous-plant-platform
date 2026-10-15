"""Optional HES simulator protection supervisor.

NOT a safety PLC, protection relay or qualified emergency-stop system.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from simulator.hydro import HydroPlantSimulator


@dataclass(frozen=True)
class ProtectiveEvent:
    time_s: float
    reason: str
    simulated_e_stop_requested: bool


class HydroSimulationSupervisor:
    def __init__(self):
        self.latched_reason: str | None = None
        self.events: list[ProtectiveEvent] = []

    @staticmethod
    def _check(sim: HydroPlantSimulator) -> str | None:
        state = sim.snapshot()

        if not state.grid_available:
            return "GRID_UNAVAILABLE"

        if state.maintenance_lock:
            return "MAINTENANCE_LOCK"

        if state.headpond_level_pct < 20:
            return "LOW_HEADPOND"

        if state.emergency_stop:
            return "E_STOP_ACTIVE"

        for unit in state.units:
            values = (
                unit.active_power_mw,
                unit.rpm,
                unit.flow_m3_s,
                unit.bearing_temperature_c,
                unit.generator_temperature_c,
                unit.vibration_mm_s,
            )

            if any(not isfinite(v) for v in values):
                return "NONFINITE_SENSOR_" + unit.unit_id

            if unit.fault or not unit.ready:
                return "UNIT_FAULT_" + unit.unit_id

            if unit.bearing_temperature_c >= 75:
                return "HIGH_BEARING_TEMPERATURE_" + unit.unit_id

            if unit.vibration_mm_s >= 7:
                return "HIGH_VIBRATION_" + unit.unit_id

        return None

    def guarded_tick(self, sim: HydroPlantSimulator):
        reason = self._check(sim)

        if reason and self.latched_reason is None:
            self.latched_reason = reason
            sim.set_emergency_stop(True)

            self.events.append(
                ProtectiveEvent(
                    sim.snapshot().simulation_time_s,
                    reason,
                    True,
                )
            )

        elif (
            self.latched_reason is not None
            and not sim.snapshot().emergency_stop
        ):
            sim.set_emergency_stop(True)

        return sim.tick()

    def reset(
        self,
        sim: HydroPlantSimulator,
        *,
        operator_acknowledged: bool = False,
    ):
        if operator_acknowledged is not True:
            raise PermissionError(
                "Explicit simulated operator acknowledgement required"
            )

        if self.latched_reason is None:
            return

        snap = sim.snapshot()

        if not snap.emergency_stop:
            raise ValueError(
                "Expected latched simulated E-stop"
            )

        sim.set_emergency_stop(False)
        reason = self._check(sim)

        if reason is not None:
            sim.set_emergency_stop(True)
            raise ValueError(
                "Cannot reset: " + reason
            )

        self.latched_reason = None

        self.events.append(
            ProtectiveEvent(
                sim.snapshot().simulation_time_s,
                "OPERATOR_ACKNOWLEDGED_RESET",
                False,
            )
        )
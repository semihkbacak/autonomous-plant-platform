"""v0.8: simulator-only fail-closed telemetry supervisor.

Reject suspicious steps without touching real devices.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
)


@dataclass(frozen=True)
class SupervisorDecision:
    allowed: bool
    code: str
    latched: bool


class GESSimulationSupervisor:

    def __init__(
        self,
        max_ghi_w_m2: float = 1500.0,
        max_wind_m_s: float = 75.0,
    ):
        if not (
            0 < max_ghi_w_m2 <= 2500
            and 0 < max_wind_m_s <= 100
        ):
            raise ValueError(
                "Invalid telemetry thresholds"
            )

        self.max_ghi_w_m2 = max_ghi_w_m2
        self.max_wind_m_s = max_wind_m_s

        self.last_end_utc: datetime | None = None
        self.latched_fault: str | None = None
        self.events: list[str] = []

    def inspect(
        self,
        item: SolarIntervalInput,
    ) -> SupervisorDecision:

        if self.latched_fault is not None:
            return SupervisorDecision(
                False,
                self.latched_fault,
                True,
            )

        try:
            a = item.start_utc
            b = item.end_utc
            w = item.weather
            ir = w.irradiance

            if (
                a.tzinfo is None
                or b.tzinfo is None
                or a.utcoffset() != timedelta(0)
                or b.utcoffset() != timedelta(0)
                or b - a != timedelta(minutes=15)
                or ir.timestamp != b
                or (
                    self.last_end_utc is not None
                    and a != self.last_end_utc
                )
            ):
                reason = "TELEMETRY_TIMESTAMP_INVALID"

            elif any(
                not isfinite(v)
                for v in (
                    ir.ghi_w_m2,
                    ir.dni_w_m2,
                    ir.dhi_w_m2,
                    w.ambient_temperature_c,
                    w.wind_speed_m_s,
                )
            ):
                reason = "TELEMETRY_NONFINITE"

            elif (
                not 0 <= ir.ghi_w_m2 <= self.max_ghi_w_m2
                or not 0 <= ir.dni_w_m2 <= 1600
                or not 0 <= ir.dhi_w_m2 <= self.max_ghi_w_m2
                or not -70 <= w.ambient_temperature_c <= 90
                or not 0 <= w.wind_speed_m_s <= self.max_wind_m_s
            ):
                reason = "TELEMETRY_RANGE_INVALID"

            else:
                reason = None

        except (
            AttributeError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            reason = "TELEMETRY_MALFORMED"

        if reason:
            self.latched_fault = reason
            self.events.append(reason)

            return SupervisorDecision(
                False, reason, True
            )

        self.last_end_utc = item.end_utc

        return SupervisorDecision(
            True, "ACCEPTED", False
        )

    def reset(
        self,
        *,
        operator_acknowledged: bool = False,
    ) -> None:

        if operator_acknowledged is not True:
            raise PermissionError(
                "Explicit simulation operator acknowledgement required"
            )

        self.latched_fault = None
        self.last_end_utc = None

        self.events.append(
            "SIMULATED_OPERATOR_RESET"
        )

    def guarded_step(
        self,
        simulator,
        item: SolarIntervalInput,
    ):
        """Run a validated step without physical equipment access."""

        previous_end = self.last_end_utc
        decision = self.inspect(item)

        if not decision.allowed:
            raise ValueError(
                f"Simulation telemetry blocked: {decision.code}"
            )

        try:
            return simulator.step(item)

        except Exception:
            self.last_end_utc = previous_end
            self.latched_fault = "SIMULATION_STEP_FAILED"

            self.events.append(
                self.latched_fault
            )

            raise
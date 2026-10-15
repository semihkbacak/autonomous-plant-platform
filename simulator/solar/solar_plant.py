from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Sequence

from simulator.solar.inverter import(
    InverterConfig,
    InverterResult,
    simulate_inverter,

)
@dataclass(frozen=True)
class SolarInverterInput:
    """
    Bir inverterin anlık DC giriş verileri.

    Bu veriler ileride PV dizi modelinden gelecek.
    """

    inverter_id: str
    dc_power_kw: float
    dc_voltage_v: float

    fault_active: bool = False
    maintenance_lock: bool = False


@dataclass(frozen=True)
class SolarPlantReport:
    """
    Çoklu inverterli GES simülasyon sonucu.
    """

    requested_target_kw: float | None

    available_power_kw: float
    dispatched_power_kw: float

    curtailed_power_kw: float
    unserved_target_kw: float

    grid_available: bool
    emergency_stop: bool

    inverter_results: tuple[InverterResult, ...]
    reasons: tuple[str, ...]


class SolarPlantSimulator:
    """
    Çoklu inverterli GES için ilk tesis seviyesi
    dispatch modeli.

    Gerçek PLC/SCADA bağlantısı içermez.
    """

    def __init__(
        self,
        inverters: Sequence[InverterConfig],
    ) -> None:

        if not inverters:
            raise ValueError(
                "At least one inverter is required"
            )

        ids = [
            inverter.inverter_id
            for inverter in inverters
        ]

        if len(ids) != len(set(ids)):
            raise ValueError(
                "Duplicate inverter IDs"
            )

        self.inverters = tuple(inverters)

    def simulate(
        self,
        inputs: Sequence[SolarInverterInput],
        requested_target_kw: float | None = None,
        *,
        grid_available: bool = True,
        emergency_stop: bool = False,
    ) -> SolarPlantReport:

        # ------------------------------------------
        # TARGET VALIDATION
        # ------------------------------------------

        if requested_target_kw is not None:
            if (
                not isfinite(requested_target_kw)
                or requested_target_kw < 0
            ):
                raise ValueError(
                    "Invalid plant power target"
                )

        # ------------------------------------------
        # INPUT VALIDATION
        # ------------------------------------------

        input_ids = [
            item.inverter_id
            for item in inputs
        ]

        if len(input_ids) != len(set(input_ids)):
            raise ValueError(
                "Duplicate inverter telemetry"
            )

        input_map = {
            item.inverter_id: item
            for item in inputs
        }

        expected_ids = {
            item.inverter_id
            for item in self.inverters
        }

        received_ids = set(input_map)

        if expected_ids != received_ids:
            raise ValueError(
                "Missing or unknown inverter telemetry: "
                f"missing={sorted(expected_ids - received_ids)}, "
                f"unknown={sorted(received_ids - expected_ids)}"
            )

        # ------------------------------------------
        # AVAILABLE AC POWER
        # ------------------------------------------

        available_results: list[InverterResult] = []

        for config in self.inverters:
            reading = input_map[config.inverter_id]

            result = simulate_inverter(
                config=config,
                dc_power_kw=reading.dc_power_kw,
                dc_voltage_v=reading.dc_voltage_v,
                grid_available=grid_available,
                fault_active=reading.fault_active,
                maintenance_lock=reading.maintenance_lock,
            )

            # Tesis düzeyindeki emergency-stop,
            # simülatörde tüm inverterleri bloke eder.

            if emergency_stop:
                result = replace(
                    result,
                    status="BLOCKED",
                    dc_accepted_kw=0.0,
                    ac_unclipped_kw=0.0,
                    ac_available_kw=0.0,
                    ac_dispatched_kw=0.0,
                    dc_rejected_kw=0.0,
                    conversion_loss_kw=0.0,
                    clipping_loss_kw=0.0,
                    curtailment_kw=0.0,
                    reasons=(
                        *result.reasons,
                        "PLANT_EMERGENCY_STOP",
                    ),
                )

            available_results.append(result)

        total_available_kw = sum(
            item.ac_available_kw
            for item in available_results
        )

        # ------------------------------------------
        # PLANT TARGET
        # ------------------------------------------

        if requested_target_kw is None:
            deliverable_target_kw = total_available_kw
        else:
            deliverable_target_kw = min(
                requested_target_kw,
                total_available_kw,
            )

        # ------------------------------------------
        # PROPORTIONAL DISPATCH
        # ------------------------------------------

        final_results: list[InverterResult] = []

        for config, available in zip(
            self.inverters,
            available_results,
        ):

            if available.ac_available_kw <= 0:
                final_results.append(available)
                continue

            reading = input_map[config.inverter_id]

            # Nominal güç oranı yerine mevcut
            # kullanılabilir AC güç oranı kullanılır.

            share = (
                available.ac_available_kw
                / total_available_kw
            )

            inverter_target_kw = (
                deliverable_target_kw * share
            )

            result = simulate_inverter(
                config=config,
                dc_power_kw=reading.dc_power_kw,
                dc_voltage_v=reading.dc_voltage_v,
                grid_available=grid_available,
                fault_active=reading.fault_active,
                maintenance_lock=reading.maintenance_lock,
                active_power_limit_kw=inverter_target_kw,
            )

            final_results.append(result)

        # ------------------------------------------
        # TOTAL RESULTS
        # ------------------------------------------

        dispatched_kw = sum(
            item.ac_dispatched_kw
            for item in final_results
        )

        curtailed_kw = sum(
            item.curtailment_kw
            for item in final_results
        )

        unserved_kw = 0.0

        if requested_target_kw is not None:
            unserved_kw = max(
                0.0,
                requested_target_kw - dispatched_kw,
            )

        # ------------------------------------------
        # PLANT REASONS
        # ------------------------------------------

        reasons: list[str] = []

        if emergency_stop:
            reasons.append(
                "PLANT_EMERGENCY_STOP"
            )

        if not grid_available:
            reasons.append(
                "GRID_UNAVAILABLE"
            )

        if total_available_kw <= 0:
            reasons.append(
                "NO_AC_POWER_AVAILABLE"
            )

        if unserved_kw > 1e-7:
            reasons.append(
                "INSUFFICIENT_AVAILABLE_POWER"
            )

        if curtailed_kw > 1e-7:
            reasons.append(
                "CURTAILMENT_APPLIED"
            )

        return SolarPlantReport(
            requested_target_kw=requested_target_kw,
            available_power_kw=total_available_kw,
            dispatched_power_kw=dispatched_kw,
            curtailed_power_kw=curtailed_kw,
            unserved_target_kw=unserved_kw,
            grid_available=grid_available,
            emergency_stop=emergency_stop,
            inverter_results=tuple(final_results),
            reasons=tuple(reasons),
        )
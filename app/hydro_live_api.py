
"""Read-only HES live unit API.

Live unit IDs and historian run IDs are different concepts.
Simulator only. No real PLC or SCADA commands.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path


def create_hydro_live_router(simulator) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/hes/live",
        tags=["HES Live (read-only)"],
    )

    def serialize(unit) -> dict:
        return {
            "unit_id": unit.unit_id,
            "status": unit.status.value,
            "active_power_kw": round(
                unit.active_power_mw * 1000.0, 6
            ),
            "rated_power_kw": round(
                unit.rated_power_mw * 1000.0, 6
            ),
            "rpm": unit.rpm,
            "flow_m3_s": unit.flow_m3_s,
            "bearing_temperature_c": (
                unit.bearing_temperature_c
            ),
            "generator_temperature_c": (
                unit.generator_temperature_c
            ),
            "vibration_mm_s": unit.vibration_mm_s,
            "ready": unit.ready,
            "fault": unit.fault,
        }

    @router.get(
        "/units",
        summary="Canlı HES üniteleri",
        description=(
            "UNIT_1 ve UNIT_2'nin güncel sentetik "
            "durumlarını getirir. Geçmiş veritabanı "
            "koşularından bağımsızdır."
        ),
    )
    def live_units() -> dict:
        snapshot = simulator.snapshot()

        return {
            "scope": "SYNTHETIC_LIVE_HES_READ_ONLY",
            "simulation_time_s": snapshot.simulation_time_s,
            "units": [
                serialize(unit)
                for unit in snapshot.units
            ],
        }

    @router.get(
        "/units/{unit_id}",
        summary="Tek canlı HES ünitesi",
        description=(
            "unit_id, UNIT_1 veya UNIT_2 gibi ünite "
            "kimliğidir. Geçmiş sorgularındaki sayısal "
            "run_id ile karıştırılmamalıdır."
        ),
    )
    def live_unit(
        unit_id: Annotated[
            str,
            Path(
                description="Ünite kimliği, örn. UNIT_1",
                examples=["UNIT_1"],
            ),
        ],
    ) -> dict:
        snapshot = simulator.snapshot()

        for unit in snapshot.units:
            if unit.unit_id == unit_id:
                return {
                    "scope": "SYNTHETIC_LIVE_HES_READ_ONLY",
                    "simulation_time_s": (
                        snapshot.simulation_time_s
                    ),
                    **serialize(unit),
                }

        raise HTTPException(
            status_code=404,
            detail="Unknown HES unit",
        )

    return router

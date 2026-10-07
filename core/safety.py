from math import isfinite
from core.models import PlantState, UnitState, UnitStatus

MIN_HEADPOND_LEVEL_PCT = 25.0
MAX_START_TEMPERATURE_C = 75.0
MAX_START_VIBRATION_MM_S = 7.0


def start_permitted(plant: PlantState, unit: UnitState) -> tuple[bool, list[str]]:
    """Deterministic simulator-only permissive checks.

    Demo rules for the digital twin only. They are NOT real plant protection logic.
    """
    reasons: list[str] = []
    if unit.status != UnitStatus.STOPPED:
        reasons.append(
                    f"Unit status {unit.status} does not permit start"
                )
    if plant.emergency_stop:
        reasons.append("Emergency stop is active")
    if plant.maintenance_lock:
        reasons.append("Maintenance lock is active")
    if not plant.grid_available:
        reasons.append("Grid is unavailable")
    if plant.headpond_level_pct < MIN_HEADPOND_LEVEL_PCT:
        reasons.append("Headpond level is below simulator minimum")
    if not unit.ready:
        reasons.append("Unit is not ready")
    if unit.fault:
        reasons.append("Unit fault is active")
    if unit.bearing_temperature_c >= MAX_START_TEMPERATURE_C:
        reasons.append("Unit bearing temperature is too high")
    if unit.vibration_mm_s >= MAX_START_VIBRATION_MM_S:
        reasons.append("Unit vibration is too high")
    
    return (len(reasons) == 0, reasons)
# Operatörün güç hedefi talebini kontrol eder.
def power_setpoint_permitted(
    plant: PlantState,
    unit: UnitState,
    target_power_mw: float,
) -> tuple[bool, list[str]]:

    reasons: list[str] = []

    # Ünite çalışıyor olmalı.
    if unit.status != UnitStatus.RUNNING:
        reasons.append("Unit is not running")

    # Tesis güvenlik koşulları.
    if plant.emergency_stop:
        reasons.append("Emergency stop is active")

    if plant.maintenance_lock:
        reasons.append("Maintenance lock is active")

    if not plant.grid_available:
        reasons.append("Grid is unavailable")

    if unit.fault:
        reasons.append("Unit fault is active")

    # İstenen güç geçerli olmalı.
    if not isfinite(target_power_mw):
        reasons.append("Power target must be finite")

    elif not (0.0 < target_power_mw <= unit.rated_power_mw):
        reasons.append("Power target is out of range")

    return (len(reasons) == 0, reasons)

def plant_power_target_permitted(
    plant: PlantState,
    target_power_mw: float,
) -> tuple[bool, list[str]]:
    """
    Tesis toplam güç hedefinin güvenli olup
    olmadığını kontrol eder.
    """

    reasons: list[str] = []

    if plant.emergency_stop:
        reasons.append(
            "Emergency stop is active"
        )

    if plant.maintenance_lock:
        reasons.append(
            "Maintenance lock is active"
        )

    if not plant.grid_available:
        reasons.append(
            "Grid is unavailable"
        )

    total_capacity_mw = sum(
        unit.rated_power_mw
        for unit in plant.units
    )

    if not isfinite(target_power_mw):
        reasons.append(
            "Plant power target must be finite"
        )

    elif not (
        0.0
        < target_power_mw
        <= total_capacity_mw
    ):
        reasons.append(
            "Plant power target is out of range"
        )

    return (
        len(reasons) == 0,
        reasons,
    )

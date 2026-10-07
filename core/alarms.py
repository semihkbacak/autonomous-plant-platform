from core.models import (
    AlarmEvent,
    AlarmSeverity,
    PlantState,
)


# Bunlar gerçek tesis/OEM limitleri değildir.
# Simülatör için kullanılan demo alarm eşikleridir.
DEMO_HIGH_TEMPERATURE_C = 75.0
DEMO_HIGH_VIBRATION_MM_S = 7.0


def detect_alarms(plant: PlantState) -> list[AlarmEvent]:
    alarms: list[AlarmEvent] = []

    # Tesis seviyesindeki alarm.
    if not plant.grid_available:
        alarms.append(
            AlarmEvent(
                code="GRID_LOSS",
                severity=AlarmSeverity.CRITICAL,
                message="Grid is unavailable",
            )
        )

    # Ünite seviyesindeki alarmlar.
    for unit in plant.units:

        if unit.fault:
            alarms.append(
                AlarmEvent(
                    code="UNIT_FAULT",
                    severity=AlarmSeverity.CRITICAL,
                    message="Unit fault is active",
                    unit_id=unit.unit_id,
                )
            )

        if unit.bearing_temperature_c >= DEMO_HIGH_TEMPERATURE_C:
            alarms.append(
                AlarmEvent(
                    code="HIGH_BEARING_TEMPERATURE",
                    severity=AlarmSeverity.WARNING,
                    message="Bearing temperature is high",
                    unit_id=unit.unit_id,
                )
            )

        if unit.vibration_mm_s >= DEMO_HIGH_VIBRATION_MM_S:
            alarms.append(
                AlarmEvent(
                    code="HIGH_VIBRATION",
                    severity=AlarmSeverity.WARNING,
                    message="Unit vibration is high",
                    unit_id=unit.unit_id,
                )
            )

    return alarms
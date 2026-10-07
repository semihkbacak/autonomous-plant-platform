from core.models import (
    AlarmSeverity,
    AnomalyFinding,
    PlantState,
    UnitStatus,
)


# ============================================================
# DEMO ANOMALY THRESHOLDS
# ============================================================

# Bunlar gerçek HES/OEM limitleri değildir.
# Simülatör için sentetik demo eşikleridir.

BEARING_ANOMALY_START_C = 65.0
BEARING_CRITICAL_C = 75.0

VIBRATION_ANOMALY_START_MM_S = 4.0
VIBRATION_CRITICAL_MM_S = 7.0

FREQUENCY_ANOMALY_START_HZ = 0.15
FREQUENCY_CRITICAL_HZ = 0.50


def _normalized_score(
    value: float,
    warning_start: float,
    critical_value: float,
) -> float:
    """
    Değeri 0-1 arasında basit risk skoruna çevirir.
    """

    if value <= warning_start:
        return 0.0

    if value >= critical_value:
        return 1.0

    score = (
        value - warning_start
    ) / (
        critical_value - warning_start
    )

    return max(
        0.0,
        min(
            1.0,
            score,
        ),
    )


def detect_anomalies(
    plant: PlantState,
) -> list[AnomalyFinding]:
    """
    HES sensörlerini inceleyerek olağandışı
    durumları bulur.

    Bu katman yalnızca analiz yapar.
    Kontrol komutu göndermez.
    """

    findings: list[AnomalyFinding] = []

    for unit in plant.units:

        # ====================================================
        # BEARING TEMPERATURE
        # ====================================================

        if (
            unit.bearing_temperature_c
            >= BEARING_ANOMALY_START_C
        ):
            score = _normalized_score(
                value=unit.bearing_temperature_c,
                warning_start=BEARING_ANOMALY_START_C,
                critical_value=BEARING_CRITICAL_C,
            )

            severity = (
                AlarmSeverity.CRITICAL
                if (
                    unit.bearing_temperature_c
                    >= BEARING_CRITICAL_C
                )
                else AlarmSeverity.WARNING
            )

            findings.append(
                AnomalyFinding(
                    code="BEARING_TEMPERATURE_ANOMALY",
                    severity=severity,
                    score=score,
                    message=(
                        "Bearing temperature is "
                        "outside the normal demo range"
                    ),
                    unit_id=unit.unit_id,
                )
            )

        # ====================================================
        # VIBRATION
        # ====================================================

        if (
            unit.vibration_mm_s
            >= VIBRATION_ANOMALY_START_MM_S
        ):
            score = _normalized_score(
                value=unit.vibration_mm_s,
                warning_start=(
                    VIBRATION_ANOMALY_START_MM_S
                ),
                critical_value=(
                    VIBRATION_CRITICAL_MM_S
                ),
            )

            severity = (
                AlarmSeverity.CRITICAL
                if (
                    unit.vibration_mm_s
                    >= VIBRATION_CRITICAL_MM_S
                )
                else AlarmSeverity.WARNING
            )

            findings.append(
                AnomalyFinding(
                    code="VIBRATION_ANOMALY",
                    severity=severity,
                    score=score,
                    message=(
                        "Vibration is outside "
                        "the normal demo range"
                    ),
                    unit_id=unit.unit_id,
                )
            )

        # ====================================================
        # FREQUENCY
        # ====================================================

        # Frekansı yalnızca çalışan ünitede değerlendir.
        # STOPPED ünitede frequency = 0 olması normaldir.
        if (
            unit.status
            == UnitStatus.RUNNING
        ):
            frequency_error_hz = abs(
                unit.frequency_hz - 50.0
            )

            if (
                frequency_error_hz
                >= FREQUENCY_ANOMALY_START_HZ
            ):
                score = _normalized_score(
                    value=frequency_error_hz,
                    warning_start=(
                        FREQUENCY_ANOMALY_START_HZ
                    ),
                    critical_value=(
                        FREQUENCY_CRITICAL_HZ
                    ),
                )

                severity = (
                    AlarmSeverity.CRITICAL
                    if (
                        frequency_error_hz
                        >= FREQUENCY_CRITICAL_HZ
                    )
                    else AlarmSeverity.WARNING
                )

                findings.append(
                    AnomalyFinding(
                        code="FREQUENCY_ANOMALY",
                        severity=severity,
                        score=score,
                        message=(
                            "Generator frequency "
                            "deviation detected"
                        ),
                        unit_id=unit.unit_id,
                    )
                )

    return findings
from core.models import (
    AlarmEvent,
    AlarmSeverity,
    AnomalyFinding,
    DecisionPriority,
    DecisionRecommendation,
    MLAnomalyFinding,
    PlantState,
)


def build_decision_recommendations(
    plant: PlantState,
    alarms: list[AlarmEvent],
    anomalies: list[AnomalyFinding],
    ml_anomalies: list[MLAnomalyFinding] | None = None,
) -> list[DecisionRecommendation]:
    """
    Alarm, rule-based anomaly ve ML anomaly
    sonuçlarından operatöre öneriler üretir.

    Bu fonksiyon PLC/SCADA komutu göndermez.
    """

    recommendations: list[
        DecisionRecommendation
    ] = []

    # ========================================================
    # EMERGENCY STOP
    # ========================================================

    if plant.emergency_stop:
        recommendations.append(
            DecisionRecommendation(
                action="HOLD_AUTONOMOUS_COMMANDS",
                priority=DecisionPriority.CRITICAL,
                reason="Emergency stop is active",
            )
        )

    # ========================================================
    # GRID LOSS
    # ========================================================

    if not plant.grid_available:
        recommendations.append(
            DecisionRecommendation(
                action="KEEP_GENERATION_BLOCKED",
                priority=DecisionPriority.CRITICAL,
                reason="Grid is unavailable",
            )
        )

    # ========================================================
    # ACTIVE CRITICAL ALARMS
    # ========================================================

    for alarm in alarms:

        if (
            alarm.severity
            == AlarmSeverity.CRITICAL
        ):
            recommendations.append(
                DecisionRecommendation(
                    action="OPERATOR_REVIEW_REQUIRED",
                    priority=DecisionPriority.CRITICAL,
                    reason=alarm.message,
                    unit_id=alarm.unit_id,
                )
            )

    # ========================================================
    # RULE-BASED ANOMALIES
    # ========================================================

    for anomaly in anomalies:

        if (
            anomaly.severity
            == AlarmSeverity.CRITICAL
        ):
            priority = (
                DecisionPriority.CRITICAL
            )
        else:
            priority = (
                DecisionPriority.WARNING
            )

        recommendations.append(
            DecisionRecommendation(
                action="INSPECT_UNIT",
                priority=priority,
                reason=(
                    f"{anomaly.message}; "
                    f"score={anomaly.score:.2f}"
                ),
                unit_id=anomaly.unit_id,
            )
        )

    # ========================================================
    # ML ANOMALIES
    # ========================================================

    if ml_anomalies is None:
        ml_anomalies = []

    for finding in ml_anomalies:

        # Normal olarak sınıflandırılmış ünite için
        # operatör önerisi üretme.
        if not finding.is_anomaly:
            continue

        if finding.anomaly_score >= 0.80:
            priority = (
                DecisionPriority.CRITICAL
            )
        else:
            priority = (
                DecisionPriority.WARNING
            )

        recommendations.append(
            DecisionRecommendation(
                action="REVIEW_ML_ANOMALY",
                priority=priority,
                reason=(
                    f"{finding.model_name} detected "
                    f"anomalous unit behaviour; "
                    f"score={finding.anomaly_score:.2f}"
                ),
                unit_id=finding.unit_id,
            )
        )

    # ========================================================
    # NORMAL OPERATION
    # ========================================================

    if not recommendations:
        recommendations.append(
            DecisionRecommendation(
                action="CONTINUE_NORMAL_OPERATION",
                priority=DecisionPriority.INFO,
                reason=(
                    "No active safety, rule-based "
                    "or ML anomaly condition detected"
                ),
            )
        )

    return recommendations
from core.anomaly import detect_anomalies
from core.decision import build_decision_recommendations
from core.scheduler import total_active_power_mw
from ml.anomaly_model import evaluate_plant_with_model
from simulator.hydro import HydroPlantSimulator
from simulator.scenarios import ScenarioType


def print_separator(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def print_plant(sim: HydroPlantSimulator) -> None:
    plant = sim.snapshot()

    print(
        f"Simulation time : {plant.simulation_time_s:.0f} s"
    )

    print(
        f"Plant power     : "
        f"{total_active_power_mw(plant):.2f} MW"
    )

    print(
        f"Plant target    : "
        f"{sim.plant_power_target_mw}"
    )

    for unit in plant.units:
        print(
            f"{unit.unit_id} | "
            f"{unit.status} | "
            f"P={unit.active_power_mw:.2f} MW | "
            f"Setpoint={unit.power_setpoint_mw} | "
            f"Needle={unit.needle_opening_pct:.1f}% | "
            f"Flow={unit.flow_m3_s:.2f} m3/s"
        )


def main() -> None:
    print_separator(
        "AUTONOMOUS PLANT PLATFORM - HES DEMO"
    )

    sim = HydroPlantSimulator()

    print(
        "Simulator created."
    )

    print_plant(sim)

    # ========================================================
    # 1. PLANT POWER TARGET
    # ========================================================

    print_separator(
        "1 - PLANT TARGET: 20 MW"
    )

    result = sim.request_plant_power_target(
        20.0
    )

    print(
        result.model_dump()
    )

    # Scheduler + START + Governor çalışsın.
    for _ in range(15):
        sim.tick()

    print_plant(sim)

    # ========================================================
    # 2. ALARMS
    # ========================================================

    print_separator(
        "2 - ACTIVE ALARMS"
    )

    alarms = sim.active_alarms()

    if alarms:
        for alarm in alarms:
            print(
                alarm.model_dump()
            )
    else:
        print(
            "No active alarms."
        )

    # ========================================================
    # 3. RULE-BASED ANOMALY
    # ========================================================

    print_separator(
        "3 - RULE-BASED ANOMALY ANALYSIS"
    )

    plant = sim.snapshot()

    rule_anomalies = detect_anomalies(
        plant
    )

    if rule_anomalies:
        for finding in rule_anomalies:
            print(
                finding.model_dump()
            )
    else:
        print(
            "No rule-based anomaly detected."
        )

    # ========================================================
    # 4. ML ANOMALY
    # ========================================================

    print_separator(
        "4 - ISOLATION FOREST ML ANALYSIS"
    )

    ml_anomalies = (
        evaluate_plant_with_model(
            plant
        )
    )

    for finding in ml_anomalies:
        print(
            finding.model_dump()
        )

    # ========================================================
    # 5. DECISION ENGINE
    # ========================================================

    print_separator(
        "5 - DECISION ENGINE"
    )

    decisions = (
        build_decision_recommendations(
            plant=plant,
            alarms=alarms,
            anomalies=rule_anomalies,
            ml_anomalies=ml_anomalies,
        )
    )

    for decision in decisions:
        print(
            decision.model_dump()
        )

    # ========================================================
    # 6. GRID LOSS SCENARIO
    # ========================================================

    print_separator(
        "6 - GRID LOSS SCENARIO"
    )

    sim.apply_scenario(
        ScenarioType.GRID_LOSS,
        seed=1,
    )

    plant = sim.snapshot()

    print(
        f"Grid available: "
        f"{plant.grid_available}"
    )

    alarms = sim.active_alarms()

    for alarm in alarms:
        print(
            "ALARM:",
            alarm.model_dump(),
        )

    # ========================================================
    # 7. DECISION AFTER GRID LOSS
    # ========================================================

    print_separator(
        "7 - DECISION AFTER GRID LOSS"
    )

    rule_anomalies = detect_anomalies(
        plant
    )

    ml_anomalies = (
        evaluate_plant_with_model(
            plant
        )
    )

    decisions = (
        build_decision_recommendations(
            plant=plant,
            alarms=alarms,
            anomalies=rule_anomalies,
            ml_anomalies=ml_anomalies,
        )
    )

    for decision in decisions:
        print(
            decision.model_dump()
        )

    # ========================================================
    # 8. ALARM HISTORY
    # ========================================================

    print_separator(
        "8 - ALARM HISTORY"
    )

    for entry in sim.alarm_history():
        print(
            entry.model_dump()
        )

    print_separator(
        "DEMO FINISHED"
    )

    print(
        "No real PLC, SCADA or OT equipment "
        "was contacted."
    )


if __name__ == "__main__":
    main()
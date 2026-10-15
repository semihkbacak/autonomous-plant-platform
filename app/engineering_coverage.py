"""Evidence-aware engineering coverage registry: software scope, not site certification."""
from __future__ import annotations

# NONE of these entries are proof of OEM or field validation.
ITEMS = [
    ("GES", "54_CASE_SYNTHETIC_MATRIX", "IMPLEMENTED", "v1.0 scenario database acceptance"),
    ("GES", "MPPT_MULTICHANNEL", "IMPLEMENTED", "Integrated multi-MPPT synthetic accounting"),
    ("GES", "PQ_DISPATCH", "IMPLEMENTED", "Synthetic inverter P/Q dispatch"),
    ("GES", "OEM_DE_SOTO_CALIBRATION", "NOT_VERIFIED", "No validated OEM coefficients or model-ready pairs"),
    ("GES", "INVERTER_EFFICIENCY_THERMAL", "APPROXIMATION", "Opt-in supplied screening curves, not OEM model"),
    ("GES", "FULL_PARALLEL_BYPASS_SHADING", "NOT_IMPLEMENTED", "Detailed bypass/string nonlinear MPP remains open"),
    ("GES", "DC_ISOLATION_ARC_GROUND_PROTECTION", "NOT_IMPLEMENTED", "Real protection requires qualified equipment and tests"),
    ("GES", "GRID_CODE_VOLTAGE_FREQUENCY", "NOT_VERIFIED", "Site-specific grid code and equipment certification"),
    ("GES", "INVERTER_TELEMETRY_LOSS", "NOT_IMPLEMENTED", "No live OT telemetry quality failover"),
    ("GES", "365_DAY_SYNTHETIC_STRESS", "IMPLEMENTED", "Not a production forecast or field comparison"),
    ("HES", "12_CASE_SYNTHETIC_MATRIX", "IMPLEMENTED", "v1.0 recorded dynamic scenarios"),
    ("HES", "GOVERNOR_AND_PERMISSIVES", "IMPLEMENTED", "Simulated Pelton governor and interlocks"),
    ("HES", "WATER_HAMMER_PENSTOCK_TRANSIENT", "NOT_IMPLEMENTED", "Requires parameterized transient hydraulic PDE/HIL"),
    ("HES", "REAL_TURBINE_EFFICIENCY_MAP", "NOT_VERIFIED", "Requires OEM hill charts and site data"),
    ("HES", "RESERVOIR_CATCHMENT_DISPATCH", "NOT_IMPLEMENTED", "No calibrated inflow/rights/environment constraints"),
    ("HES", "LOAD_REJECTION_OVERSPEED", "APPROXIMATION", "Protective demo; no qualified overspeed transient physics"),
    ("HES", "SYNCHRONIZATION_GRID_PROTECTION", "NOT_VERIFIED", "Protection relay and grid operator requirements"),
    ("HES", "365_DAY_STEADY_SYNTHETIC", "IMPLEMENTED", "15-minute steady-state only, not annual dynamic transient"),
    ("RES", "12_CASE_SYNTHETIC_MATRIX", "IMPLEMENTED", "v1.0 recorded synthetic scenarios"),
    ("RES", "JENSEN_WAKE_SCREENING", "APPROXIMATION", "Wake proxy only, not site-calibrated CFD"),
    ("RES", "HIGH_WIND_RESTART", "IMPLEMENTED", "Synthetic turbine protection transitions"),
    ("RES", "PITCH_ACTUATOR_FAILURE", "NOT_IMPLEMENTED", "Mechanical/electrical dynamics absent"),
    ("RES", "YAW_SENSOR_ACTUATOR_FAILURE", "NOT_IMPLEMENTED", "No high-fidelity yaw dynamics"),
    ("RES", "TOWER_DRIVETRAIN_LOAD_FATIGUE", "NOT_IMPLEMENTED", "Aeroelastic loads not modeled"),
    ("RES", "REAL_OEM_POWER_CURVE", "NOT_VERIFIED", "Measured curve and density correction required"),
    ("RES", "365_DAY_SYNTHETIC_WIND", "IMPLEMENTED", "Synthetic 15-minute input"),
    ("PLATFORM", "THREE_PLANT_DASHBOARD", "IMPLEMENTED", "Independent simulation clocks; no total live energy"),
    ("PLATFORM", "UNIFIED_SIMULATOR_ALARM_VIEW", "IMPLEMENTED", "Volatile simulator-only aggregation"),
    ("PLATFORM", "ALIGNED_PORTFOLIO_ENERGY_STUDY", "IMPLEMENTED", "Only when the three inputs are strictly time-aligned"),
    ("PLATFORM", "TELEMETRY_FINITE_AND_ACCOUNTING_QA", "IMPLEMENTED", "Synthetic output post-checks, no measured-sensor validation"),
    ("PLATFORM", "FAULT_INJECTION_TELEMETRY_QA", "IMPLEMENTED", "Software validator faults, not physical plant faults"),
    ("PLATFORM", "OPERATOR_IDENTITY_AND_RBAC", "NOT_IMPLEMENTED", "No production IAM or multi-user roles"),
    ("PLATFORM", "END_TO_END_COMMAND_AUDIT", "APPROXIMATION", "Local HTTP attempt ledger; not tamper-proof"),
    ("PLATFORM", "READ_ONLY_SHADOW_OT_ADAPTER", "NOT_IMPLEMENTED", "CSV offline research only; no connected OT adapter"),
    ("PLATFORM", "INDEPENDENT_SIS_PROTECTION", "NOT_VERIFIED", "Cannot certify without an authorized site/SIS assessment"),
    ("PLATFORM", "WINDOWS_EXE_CLIENT", "NOT_IMPLEMENTED", "Build/test on Windows after stable API and client spec"),
    ("PLATFORM", "SITE_HIL_SAT_FAT_CYBER", "NOT_VERIFIED", "Requires authorized plant engineering, FAT/SAT and cybersecurity"),
]


def coverage():
    rows = [{"plant": p, "feature": name, "status": status, "evidence_limit": reason}
            for p, name, status, reason in ITEMS]
    by_state = {state: sum(x["status"] == state for x in rows)
                for state in ("IMPLEMENTED", "APPROXIMATION", "NOT_IMPLEMENTED", "NOT_VERIFIED")}
    return {"scope": "SOFTWARE_SELF_ASSESSMENT_NOT_FIELD_CERTIFICATION",
            "field_ready": False, "oem_ready": False,
            "readiness_to_control_actual_plant": False,
            "totals": by_state, "items": rows}

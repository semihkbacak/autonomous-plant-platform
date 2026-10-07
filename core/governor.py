def calculate_power_error_mw(
    target_power_mw: float,
    actual_power_mw: float,
) -> float:
    return target_power_mw - actual_power_mw

def calculate_governor_correction_pct(
    power_error_mw: float,
    kp: float,
) -> float:
    return power_error_mw * kp
kp = 2.0
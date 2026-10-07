from core.governor import (
    calculate_power_error_mw,
    calculate_governor_correction_pct,
)


def test_positive_power_error_when_generation_is_low():
    error = calculate_power_error_mw(
        target_power_mw=12.0,
        actual_power_mw=10.0,
    )

    assert error == 2.0


def test_negative_power_error_when_generation_is_high():
    error = calculate_power_error_mw(
        target_power_mw=10.0,
        actual_power_mw=12.0,
    )

    assert error == -2.0


def test_governor_correction_uses_power_error():
    correction = calculate_governor_correction_pct(
        power_error_mw=2.0,
        kp=2.0,
    )

    assert correction == 4.0
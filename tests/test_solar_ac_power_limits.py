
import pytest

from simulator.solar.ac_power_limits import (
    ACOperatingRequest,
    evaluate_ac_power,
)


def test_100_kva_with_60_kvar_limits_active_power():

    result = evaluate_ac_power(
        ACOperatingRequest(
            nameplate_kva=100,
            requested_active_kw=90,
            requested_reactive_kvar=60,
        )
    )

    assert result.max_active_kw == pytest.approx(80)
    assert result.candidate_active_kw == pytest.approx(80)
    assert result.active_shortfall_kw == pytest.approx(10)
    assert result.candidate_power_factor == pytest.approx(0.8)
    assert result.status == "ACTIVE_POWER_LIMITED"


def test_negative_reactive_power_has_same_magnitude_limit():

    positive = evaluate_ac_power(
        ACOperatingRequest(100, 90, 60)
    )

    negative = evaluate_ac_power(
        ACOperatingRequest(100, 90, -60)
    )

    assert negative.max_active_kw == pytest.approx(
        positive.max_active_kw
    )
    assert negative.requested_reactive_kvar == -60


def test_request_inside_apparent_power_envelope():

    result = evaluate_ac_power(
        ACOperatingRequest(100, 70, 60)
    )

    assert result.request_is_feasible
    assert result.candidate_active_kw == pytest.approx(70)
    assert result.active_shortfall_kw == 0


def test_reactive_request_over_limit_is_infeasible():

    result = evaluate_ac_power(
        ACOperatingRequest(100, 20, 110)
    )

    assert not result.request_is_feasible
    assert result.status == "REACTIVE_REQUEST_INFEASIBLE"
    assert result.candidate_active_kw is None


def test_external_temperature_limit_reduces_capacity():

    result = evaluate_ac_power(
        ACOperatingRequest(
            nameplate_kva=100,
            requested_active_kw=80,
            requested_reactive_kvar=42,
            temperature_limit_kva=70,
            temperature_limit_source="TEST_FIXTURE",
        )
    )

    assert result.applied_kva_limit == 70
    assert result.max_active_kw == pytest.approx(56)
    assert result.candidate_active_kw == pytest.approx(56)
    assert result.active_shortfall_kw == pytest.approx(24)

    assert "THERMAL_KVA_LIMIT_APPLIED" in result.warnings


def test_temperature_limit_requires_source():

    with pytest.raises(ValueError):
        evaluate_ac_power(
            ACOperatingRequest(
                nameplate_kva=100,
                requested_active_kw=70,
                requested_reactive_kvar=0,
                temperature_limit_kva=80,
            )
        )


def test_temperature_limit_cannot_exceed_nameplate():

    with pytest.raises(ValueError):
        evaluate_ac_power(
            ACOperatingRequest(
                nameplate_kva=100,
                requested_active_kw=70,
                requested_reactive_kvar=0,
                temperature_limit_kva=120,
                temperature_limit_source="TEST_FIXTURE",
            )
        )


def test_invalid_values_are_rejected():

    for bad_value in (
        -1,
        float("nan"),
        float("inf"),
    ):
        with pytest.raises(ValueError):
            evaluate_ac_power(
                ACOperatingRequest(
                    nameplate_kva=100,
                    requested_active_kw=bad_value,
                    requested_reactive_kvar=0,
                )
            )


def test_zero_reactive_power_and_unknown_derating():

    result = evaluate_ac_power(
        ACOperatingRequest(
            nameplate_kva=100,
            requested_active_kw=100,
            requested_reactive_kvar=0,
        )
    )

    assert result.max_active_kw == pytest.approx(100)
    assert result.request_is_feasible

    assert (
        "THERMAL_CAPABILITY_NOT_VERIFIED"
        in result.warnings
    )

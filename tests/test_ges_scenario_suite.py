
"""GES scenario laboratory regression tests."""

import pytest

from demo_ges_scenarios import (
    Case,
    catalog,
    simulate_case,
    validate_report,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


@pytest.fixture(scope="module")
def daylight():

    rows = load_weather_intervals_csv(
        "data/solar/demo_weather_15m.csv"
    )

    return max(
        rows,
        key=lambda r: r.weather.irradiance.ghi_w_m2,
    ).weather


def test_scenario_catalog_is_complete():

    scenarios = catalog()

    assert len(scenarios) == 150

    assert len({
        c.name for c in scenarios
    }) == 150

    assert len({
        c.family for c in scenarios
    }) >= 10


def test_no_sun_produces_zero_power(daylight):

    report = simulate_case(
        Case(
            "no_sun",
            "test",
            irradiance=0,
        ),
        daylight,
    )

    assert report.plant.dispatched_power_kw == 0

    assert all(
        r.dc.dc_accepted_kw == 0
        for r in report.mppt_reports
    )


@pytest.mark.parametrize(
    "case",
    [
        Case("grid", "test", grid=False),
        Case("stop", "test", stop=True),
        Case(
            "faults",
            "test",
            faults=("INV_1", "INV_2"),
        ),
        Case(
            "locks",
            "test",
            locks=("INV_1", "INV_2"),
        ),
        Case("zero_target", "test", target_kw=0),
    ],
)
def test_blocked_or_curtailed_conditions(
    daylight,
    case,
):

    report = simulate_case(
        case,
        daylight,
    )

    assert report.plant.dispatched_power_kw == 0


def test_pq_reduces_or_preserves_active_power(
    daylight,
):

    baseline = simulate_case(
        Case("q0", "test", q_kvar=0),
        daylight,
    )

    limited = simulate_case(
        Case("q8", "test", q_kvar=8),
        daylight,
    )

    assert (
        limited.plant.dispatched_power_kw
        <= baseline.plant.dispatched_power_kw + 1e-8
    )


def test_one_mppt_optical_loss_reduces_dc(
    daylight,
):

    baseline = simulate_case(
        Case("normal", "test"),
        daylight,
    )

    affected = simulate_case(
        Case(
            "optical_loss",
            "test",
            transmission=0,
            channel=("INV_1", 1),
        ),
        daylight,
    )

    base_dc = sum(
        x.dc.dc_accepted_kw
        for x in baseline.mppt_reports
    )

    affected_dc = sum(
        x.dc.dc_accepted_kw
        for x in affected.mppt_reports
    )

    assert affected_dc < base_dc


def test_different_mppt_string_lengths(
    daylight,
):

    report = simulate_case(
        Case(
            "different_lengths",
            "test",
            modules_per_string=9,
            channel=("INV_1", 2),
        ),
        daylight,
    )

    channels = report.mppt_reports[0].dc.channels

    assert (
        channels[0].voltage_v
        != pytest.approx(channels[1].voltage_v)
    )


@pytest.mark.parametrize(
    "case",
    [
        Case(
            "negative_wind",
            "test",
            wind_m_s=-1,
        ),
        Case(
            "unknown_inverter",
            "test",
            faults=("UNKNOWN",),
        ),
        Case(
            "invalid_q",
            "test",
            q_kvar=11,
        ),
        Case(
            "invalid_transmission",
            "test",
            transmission=1.5,
        ),
        Case(
            "invalid_current",
            "test",
            operating_a=0,
        ),
    ],
)
def test_invalid_inputs_rejected(
    daylight,
    case,
):

    with pytest.raises((ValueError, TypeError)):
        simulate_case(
            case,
            daylight,
        )


def test_power_invariants(daylight):

    report = simulate_case(
        Case(
            "combined_test",
            "test",
            irradiance=.7,
            ambient_c=45,
            q_kvar=6,
            target_kw=5,
        ),
        daylight,
    )

    validate_report(report)

    assert (
        report.plant.dispatched_power_kw
        <= 5 + 1e-8
    )

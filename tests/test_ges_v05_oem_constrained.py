
"""OEM voltage/current envelope tests, not OEM calibration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from demo_ges_v05_oem_constrained import (
    load_envelopes,
    guarded_pipeline,
)

from demo_ges_v05_scenarios import (
    _case_pipeline,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)


AUDIT = Path(
    "outputs/ges_oem_shadow_v05/oem_shadow_audit.json"
)


@pytest.fixture(scope="module")
def oem_limits():

    if not AUDIT.is_file():
        pytest.skip(
            "OEM shadow audit file not present"
        )

    return load_envelopes(AUDIT)[0]


def midday_weather():

    samples = make_stress_intervals(1)

    return next(
        x.weather
        for x in samples
        if x.start_utc.hour == 10
    )


def test_reported_voltage_limits(oem_limits):

    assert (
        oem_limits["SMA_STP50_40"]["mppt_min_v"]
        == 500
    )

    assert (
        oem_limits["SUNGROW_SG110CX_V152"]["mppt_min_v"]
        == 200
    )


def test_sma_string_voltage_rejected(oem_limits):

    weather = midday_weather()

    original = _case_pipeline(
        "BASELINE_PQ8"
    ).simulate(weather)

    candidate = guarded_pipeline(
        "BASELINE_PQ8",
        "SMA_STP50_40",
        oem_limits["SMA_STP50_40"],
    ).simulate(weather)

    assert sum(
        x.dc.dc_offered_kw
        for x in original.mppt_reports
    ) > 0

    assert sum(
        x.dc.dc_offered_kw
        for x in candidate.mppt_reports
    ) > 0

    assert sum(
        x.dc.dc_accepted_kw
        for x in candidate.mppt_reports
    ) == pytest.approx(0)

    assert (
        candidate.plant.dispatched_power_kw
        == pytest.approx(0)
    )


def test_sungrow_daylight_can_deliver_synthetic_ac(
    oem_limits,
):

    candidate = guarded_pipeline(
        "BASELINE_PQ8",
        "SUNGROW_SG110CX_V152",
        oem_limits["SUNGROW_SG110CX_V152"],
    ).simulate(midday_weather())

    assert sum(
        x.dc.dc_accepted_kw
        for x in candidate.mppt_reports
    ) > 0

    assert (
        candidate.plant.dispatched_power_kw
        > 0
    )


def test_custom_current_limit_is_preserved(oem_limits):

    candidate = guarded_pipeline(
        "CURRENT_LIMIT_2A",
        "SUNGROW_SG110CX_V152",
        oem_limits["SUNGROW_SG110CX_V152"],
    )

    assert (
        candidate.mppt_configs["INV_1"]
        .limits.max_operating_a
        == 2.0
    )

    report = candidate.simulate(
        midday_weather()
    )

    for channel in report.mppt_reports[0].dc.channels:

        assert (
            channel.accepted_kw
            <= channel.voltage_v * 2 / 1000 + 1e-8
        )


def test_no_expansion_of_synthetic_mppt_window(
    oem_limits,
):

    candidate = guarded_pipeline(
        "MPPT_WINDOW_400V",
        "SUNGROW_SG110CX_V152",
        oem_limits["SUNGROW_SG110CX_V152"],
    )

    assert (
        candidate.mppt_configs["INV_1"]
        .limits.min_v >= 400
    )

    assert (
        candidate.mppt_configs["INV_1"]
        .limits.max_v <= 800
    )


def test_invalid_audit_rejected(tmp_path):

    bad = tmp_path / "audit.json"

    bad.write_text(
        json.dumps({
            "model_screening": {
                "SMA_STP50_40": {
                    "mppt_count": 6,
                    "mppt_min_v": -500,
                },
                "SUNGROW_SG110CX_V152": {},
            }
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_envelopes(bad)

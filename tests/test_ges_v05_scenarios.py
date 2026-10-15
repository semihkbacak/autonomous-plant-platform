
"""GES v0.5 scenario validations; no modification of existing DB files."""

from dataclasses import replace
from datetime import timedelta, timezone
from math import sqrt

import pytest

from demo_ges_v05_scenarios import (
    CASES,
    CASE_BY_NAME,
    _case_interval,
    _case_pipeline,
    run_case,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
)

from simulator.solar.historian import SolarHistorian
from simulator.solar.solar_stress import make_stress_intervals
from simulator.solar.solar_timeseries import SolarTimeSeriesSimulator


@pytest.fixture(scope="module")
def noon():
    # Daylight interval, from the existing synthetic stress generator.
    intervals = tuple(make_stress_intervals(1))
    assert len(intervals) == 96
    return intervals[40]


def one(name, raw, index=40):
    pipeline = _case_pipeline(name)
    sim = SolarTimeSeriesSimulator(pipeline)
    item = _case_interval(name, raw, index, pipeline)
    return sim.step(item)


def test_scenario_catalog_unique_and_broad():
    assert len(CASES) == len(CASE_BY_NAME) == 54
    assert len({case.group for case in CASES}) >= 7


@pytest.mark.parametrize(
    "name",
    [
        "GRID_LOSS_ALL",
        "GRID_LOSS_NOON",
        "ESTOP_NOON",
        "BOTH_FAULT",
    ],
)
def test_full_blockers_zero_ac(name, noon):
    record = one(name, noon)

    assert record.dispatched_power_kw == pytest.approx(0.0)
    assert record.available_power_kw == pytest.approx(0.0)

    assert all(
        x.status == "BLOCKED"
        for x in record.inverter_results
    )


@pytest.mark.parametrize(
    "name,failed_inverter",
    [
        ("INV1_FAULT_NOON", "INV_1"),
        ("INV2_FAULT_NOON", "INV_2"),
        ("MAINT_INV2_NOON", "INV_2"),
    ],
)
def test_individual_inverter_outage(name, failed_inverter, noon):
    record = one(name, noon)

    results = {
        x.inverter_id: x
        for x in record.inverter_results
    }

    assert results[failed_inverter].status == "BLOCKED"

    assert (
        results[failed_inverter].ac_dispatched_kw
        == pytest.approx(0)
    )

    assert record.dispatched_power_kw >= 0


def test_zero_sun_and_low_irradiance(noon):
    baseline = one("BASELINE_PQ8", noon)
    shadow = one("OVERCAST_30", noon)
    dark = one("NO_SUN_ALL_DAY", noon)

    assert dark.dispatched_power_kw == 0

    assert sum(
        x.dc.dc_offered_kw
        for x in dark.mppt_reports
    ) == 0

    assert (
        shadow.dispatched_power_kw
        <= baseline.dispatched_power_kw + 1e-6
    )


def test_power_targets_and_unserved_energy(noon):
    zero = one("TARGET_0", noon)
    limited = one("TARGET_4", noon)
    high = one("TARGET_UNREACHABLE", noon)

    assert zero.dispatched_power_kw == 0

    assert limited.dispatched_power_kw <= 4.0 + 1e-6

    assert high.unserved_target_kw > 0


def test_reactive_q_active_limit_and_sign(noon):
    pos = one("Q_POS_9_5", noon)
    neg = one("Q_NEG_6", noon)

    assert pos.dispatched_power_kw <= (
        2 * sqrt(100 - 9.5**2) + 1e-6
    )

    assert sorted(
        round(x.requested_reactive_kvar, 1)
        for x in neg.pq_reports
    ) == [-6, -6]

    thermal = one("Q_THERMAL_6KVA", noon)

    assert thermal.dispatched_power_kw <= (
        2 * sqrt(36 - 4**2) + 1e-6
    )


def test_mppt_low_voltage_and_high_voc(noon):
    for name, expected_reason in (
        ("SHORT_STRING", "OUTSIDE_MPPT_WINDOW"),
        ("LONG_STRING_VOC", "DC_VOC_EXCEEDS_ABSOLUTE_LIMIT"),
    ):
        record = one(name, noon)

        inv = next(
            x for x in record.mppt_reports
            if x.inverter_id == "INV_1"
        )

        channel = next(
            x for x in inv.dc.channels
            if x.channel == 1
        )

        assert channel.accepted_kw == 0
        assert expected_reason in channel.reasons


def test_synthetic_optical_loss_and_orientation(noon):
    baseline = one("BASELINE_PQ8", noon)
    soiling = one("SOILING_ALL", noon)
    oriented = one("EAST_WEST_ARRAYS", noon)

    assert soiling.dispatched_power_kw >= 0

    assert (
        soiling.dispatched_power_kw
        <= baseline.dispatched_power_kw + 1e-6
    )

    assert len(oriented.mppt_reports) == 2
    assert len(oriented.mppt_reports[0].dc.channels) == 2


@pytest.mark.parametrize(
    "bad_case",
    [
        "bad_ghi",
        "nan_ghi",
        "bad_wind",
        "nan_temp",
        "bad_target",
        "unknown_fault",
        "missing_q",
        "q_too_large",
        "bad_source",
        "bad_duration",
        "bad_weather_time",
        "non_utc_start",
    ],
)
def test_invalid_inputs_are_rejected(bad_case, noon):
    pipeline = _case_pipeline("BASELINE_PQ8")

    item = _case_interval(
        "BASELINE_PQ8",
        noon,
        40,
        pipeline,
    )

    weather = item.weather
    sample = weather.irradiance

    if bad_case == "bad_ghi":
        item = replace(
            item,
            weather=replace(
                weather,
                irradiance=replace(
                    sample,
                    ghi_w_m2=-1.0,
                ),
            ),
        )

    elif bad_case == "nan_ghi":
        item = replace(
            item,
            weather=replace(
                weather,
                irradiance=replace(
                    sample,
                    ghi_w_m2=float("nan"),
                ),
            ),
        )

    elif bad_case == "bad_wind":
        item = replace(
            item,
            weather=replace(
                weather,
                wind_speed_m_s=-1.0,
            ),
        )

    elif bad_case == "nan_temp":
        item = replace(
            item,
            weather=replace(
                weather,
                ambient_temperature_c=float("nan"),
            ),
        )

    elif bad_case == "bad_target":
        item = replace(
            item,
            requested_target_kw=-5.0,
        )

    elif bad_case == "unknown_fault":
        item = replace(
            item,
            fault_inverter_ids=frozenset({
                "NONEXISTENT"
            }),
        )

    elif bad_case == "missing_q":
        item = replace(
            item,
            reactive_requests_kvar=None,
        )

    elif bad_case == "q_too_large":
        item = replace(
            item,
            reactive_requests_kvar={
                "INV_1": 11.0,
                "INV_2": 8.0,
            },
        )

    elif bad_case == "bad_source":
        item = replace(
            item,
            weather=replace(
                weather,
                irradiance=replace(
                    sample,
                    source_type="UNKNOWN",
                ),
            ),
        )

    elif bad_case == "bad_duration":
        item = replace(
            item,
            end_utc=(
                item.end_utc
                + timedelta(minutes=1)
            ),
        )

    elif bad_case == "bad_weather_time":
        item = replace(
            item,
            weather=replace(
                weather,
                irradiance=replace(
                    sample,
                    timestamp=item.start_utc,
                ),
            ),
        )

    elif bad_case == "non_utc_start":
        item = replace(
            item,
            start_utc=item.start_utc.replace(
                tzinfo=timezone(
                    timedelta(hours=3)
                )
            ),
        )

    with pytest.raises((ValueError, TypeError)):
        SolarTimeSeriesSimulator(
            pipeline
        ).step(item)


def test_historian_records_one_scenario_atomically(
    tmp_path,
    noon,
):
    import sqlite3

    db = tmp_path / "ges_v05_scenarios.sqlite3"

    historian = SolarHistorian(db)

    result = run_case(
        CASE_BY_NAME["BASELINE_PQ8"],
        (noon,),
        historian,
    )

    assert result["run_id"] == 1

    with sqlite3.connect(db) as sql:
        for table, count in (
            ("production_intervals", 1),
            ("ges_inverter_intervals", 2),
            ("ges_mppt_intervals", 4),
            ("ges_pq_intervals", 2),
        ):
            stored = sql.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            assert stored == count

        assert sql.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []


def test_too_many_parallel_strings_rejected(noon):
    base = _case_pipeline("BASELINE_PQ8")

    configs = dict(base.mppt_configs)
    old = configs["INV_1"]

    changed = replace(
        old.channels[0],
        array=replace(
            old.channels[0].array,
            parallel_strings=old.limits.max_strings + 1,
        ),
    )

    configs["INV_1"] = replace(
        old,
        channels=(
            changed,
            *old.channels[1:],
        ),
    )

    invalid = IntegratedSolarPhysicsPipeline(
        base.site,
        base.assets,
        configs,
    )

    with pytest.raises(
        ValueError,
        match="Too many parallel strings",
    ):
        invalid.simulate(noon.weather)


def test_duplicate_mppt_channel_rejected(noon):
    base = _case_pipeline("BASELINE_PQ8")

    configs = dict(base.mppt_configs)
    old = configs["INV_1"]

    configs["INV_1"] = replace(
        old,
        channels=(
            old.channels[0],
            old.channels[0],
        ),
    )

    invalid = IntegratedSolarPhysicsPipeline(
        base.site,
        base.assets,
        configs,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate MPPT",
    ):
        invalid.simulate(noon.weather)

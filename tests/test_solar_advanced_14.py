
from pathlib import Path
from math import isclose

import pytest

from demo_ges_timeseries import (
    build_demo_pipeline,
)

from simulator.solar.component_catalog import (
    load_component_catalog,
)

from simulator.solar.multi_mppt_physics import (
    MPPTArray,
    MPPTLimits,
    calculate_multi_mppt_dc,
)

from simulator.solar.oem_model_readiness import (
    assess_oem_readiness,
    limits_from_oem_catalog,
    approximate_oem_panel_temperature,
    require_real_oem_model,
)

from simulator.solar.pq_dispatch import (
    PQCapability,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


ROOT = Path(__file__).resolve().parents[1]

WEATHER = (
    ROOT / "data/solar/demo_weather_15m.csv"
)

CATALOG = (
    ROOT
    / "data/solar/reference/ges_component_parameters.csv"
)


def demo_weather():
    return load_weather_intervals_csv(
        WEATHER
    )[1]


def demo_pq_capabilities():
    return {
        "INV_1": PQCapability(
            nameplate_kva=5.0,
            rated_active_kw=10.0,
        ),
        "INV_2": PQCapability(
            nameplate_kva=5.0,
            rated_active_kw=10.0,
        ),
    }


def test_two_mppts_have_separate_dc_results():
    pipeline = build_demo_pipeline()

    weather = demo_weather().weather

    result = calculate_multi_mppt_dc(
        site=pipeline.site,
        weather=weather,
        arrays=(
            MPPTArray(
                channel=1,
                array=pipeline.assets[0].array,
                surface=pipeline.assets[0].surface,
            ),
            MPPTArray(
                channel=2,
                array=pipeline.assets[1].array,
                surface=pipeline.assets[1].surface,
            ),
        ),
        limits=MPPTLimits(
            mppt_count=2,
            min_v=200,
            max_v=800,
            max_dc_v=1000,
            max_operating_a=30,
            max_short_circuit_a=40,
            max_strings=2,
        ),
    )

    assert len(result.channels) == 2

    assert result.dc_offered_kw > 0

    assert result.dc_accepted_kw <= (
        result.dc_offered_kw
    )

    assert isclose(
        result.dc_offered_kw,
        sum(
            channel.offered_kw
            for channel in result.channels
        ),
        abs_tol=1e-8,
    )

    assert isclose(
        result.dc_offered_kw,
        result.dc_accepted_kw
        + result.dc_rejected_kw,
        abs_tol=1e-8,
    )


def test_mppt_current_is_limited_independently():
    pipeline = build_demo_pipeline()
    weather = demo_weather().weather

    result = calculate_multi_mppt_dc(
        site=pipeline.site,
        weather=weather,
        arrays=(
            MPPTArray(
                channel=1,
                array=pipeline.assets[0].array,
                surface=pipeline.assets[0].surface,
            ),
        ),
        limits=MPPTLimits(
            mppt_count=2,
            min_v=200,
            max_v=800,
            max_dc_v=1000,
            max_operating_a=1,
            max_short_circuit_a=40,
            max_strings=2,
        ),
    )

    channel = result.channels[0]

    assert channel.accepted_kw <= (
        channel.voltage_v / 1000.0
    ) + 1e-9

    assert channel.rejected_kw > 0


def test_duplicate_mppt_channel_rejected():
    pipeline = build_demo_pipeline()
    asset = pipeline.assets[0]

    branch = MPPTArray(
        channel=1,
        array=asset.array,
        surface=asset.surface,
    )

    with pytest.raises(
        ValueError,
        match="Duplicate MPPT",
    ):
        calculate_multi_mppt_dc(
            site=pipeline.site,
            weather=demo_weather().weather,
            arrays=(branch, branch),
            limits=MPPTLimits(
                2, 200, 800, 1000, 30, 40, 2
            ),
        )


def test_real_oem_model_reports_missing_parameters():
    catalog = load_component_catalog(
        CATALOG
    )

    panel = catalog["TRINA_TSM445_NEG9R28"]
    inverter = catalog["SMA_STP50_40"]

    report = assess_oem_readiness(
        panel,
        inverter,
    )

    assert not report.real_physics_ready

    assert "PANEL:a_ref_v" in report.missing

    assert (
        "INVERTER:eta_nominal_curve_parameter"
        in report.missing
    )

    with pytest.raises(
        ValueError,
        match="Missing OEM",
    ):
        require_real_oem_model(
            panel,
            inverter,
        )


def test_sungrow_mppt_count_from_catalog():
    catalog = load_component_catalog(
        CATALOG
    )

    limits = limits_from_oem_catalog(
        catalog["SUNGROW_SG110CX_V152"]
    )

    assert limits.mppt_count == 9
    assert limits.max_dc_v == 1100
    assert limits.max_operating_a == 26
    assert limits.max_strings == 2


def test_temperature_requires_explicit_coefficients():
    catalog = load_component_catalog(
        CATALOG
    )

    panel = catalog["TRINA_TSM445_NEG9R28"]

    with pytest.raises(
        ValueError,
        match="Explicit Faiman",
    ):
        approximate_oem_panel_temperature(
            panel,
            irradiance_w_m2=800,
            ambient_c=25,
            wind_m_s=2,
        )


def test_temperature_estimate_is_labeled_approximate():
    catalog = load_component_catalog(
        CATALOG
    )

    panel = catalog["TRINA_TSM445_NEG9R28"]

    result = approximate_oem_panel_temperature(
        panel,
        irradiance_w_m2=800,
        ambient_c=25,
        wind_m_s=2,
        u0=25,
        u1=6.84,
    )

    assert result.cell_temperature_c > 25

    assert result.approx_stc_power_w > 0

    assert (
        "APPROXIMATE_STC_GAMMA_MODEL_NOT_DESOTO"
        in result.warnings
    )


def test_pq_dispatch_reduces_active_power():
    pipeline = build_demo_pipeline()
    weather = demo_weather().weather

    baseline = pipeline.simulate(
        weather
    )

    constrained = pipeline.simulate(
        weather,
        pq_capabilities=demo_pq_capabilities(),
        reactive_requests_kvar={
            "INV_1": 4.0,
            "INV_2": 4.0,
        },
    )

    assert constrained.plant.dispatched_power_kw <= 6.0 + 1e-8

    assert constrained.plant.dispatched_power_kw <= (
        baseline.plant.dispatched_power_kw
    )

    assert isclose(
        constrained.plant.dispatched_power_kw,
        sum(
            inverter.ac_dispatched_kw
            for inverter in (
                constrained.plant.inverter_results
            )
        ),
        abs_tol=1e-8,
    )


def test_zero_q_with_large_capacity_matches_legacy():
    pipeline = build_demo_pipeline()
    weather = demo_weather().weather

    baseline = pipeline.simulate(
        weather
    )

    result = pipeline.simulate(
        weather,
        pq_capabilities={
            "INV_1": PQCapability(50, 10),
            "INV_2": PQCapability(50, 10),
        },
        reactive_requests_kvar={
            "INV_1": 0,
            "INV_2": 0,
        },
    )

    assert result.plant.dispatched_power_kw == pytest.approx(
        baseline.plant.dispatched_power_kw,
        abs=1e-8,
    )


def test_reactive_request_over_kva_is_rejected():
    pipeline = build_demo_pipeline()

    with pytest.raises(
        ValueError,
        match="Reactive request infeasible",
    ):
        pipeline.simulate(
            demo_weather().weather,
            pq_capabilities=demo_pq_capabilities(),
            reactive_requests_kvar={
                "INV_1": 10.0,
                "INV_2": 4.0,
            },
        )


def test_unknown_active_rating_blocks_pq():
    pipeline = build_demo_pipeline()

    with pytest.raises(
        ValueError,
        match="Rated active power unknown",
    ):
        pipeline.simulate(
            demo_weather().weather,
            pq_capabilities={
                "INV_1": PQCapability(5, None),
                "INV_2": PQCapability(5, 10),
            },
            reactive_requests_kvar={
                "INV_1": 0,
                "INV_2": 0,
            },
        )


def test_pq_limits_reach_time_series():
    pipeline = build_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    weather_row = demo_weather()

    record = simulator.step(
        SolarIntervalInput(
            start_utc=weather_row.start_utc,
            end_utc=weather_row.end_utc,
            weather=weather_row.weather,
            pq_capabilities=demo_pq_capabilities(),
            reactive_requests_kvar={
                "INV_1": 4,
                "INV_2": 4,
            },
        )
    )

    assert record.dispatched_power_kw <= 6 + 1e-8

    assert record.dispatched_power_kw <= (
        record.available_power_kw
    )

    assert record.interval_energy_kwh == pytest.approx(
        record.dispatched_power_kw * 0.25
    )


def test_grid_loss_preserved_under_pq():
    pipeline = build_demo_pipeline()
    simulator = SolarTimeSeriesSimulator(pipeline)

    weather_row = demo_weather()

    record = simulator.step(
        SolarIntervalInput(
            start_utc=weather_row.start_utc,
            end_utc=weather_row.end_utc,
            weather=weather_row.weather,

            grid_available=False,

            pq_capabilities=demo_pq_capabilities(),

            reactive_requests_kvar={
                "INV_1": 4,
                "INV_2": 4,
            },
        )
    )

    assert record.dispatched_power_kw == 0

    assert "GRID_UNAVAILABLE" in record.active_alarms

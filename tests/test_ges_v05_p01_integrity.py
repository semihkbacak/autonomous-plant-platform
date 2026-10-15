
"""v0.5 P01: fail-closed OEM provenance and complete MPPT history."""

from dataclasses import replace
from pathlib import Path

import pytest

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)

from simulator.solar.component_catalog import (
    Component,
    ParameterRecord,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.oem_model_readiness import (
    assess_oem_readiness,
    require_real_oem_model,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


WEATHER = (
    Path(__file__).resolve().parents[1]
    / "data/solar/demo_weather_15m.csv"
)


def component_fixtures(
    *,
    model_evidence: str,
    model_source: str = "LAB-A",
):
    """Populated parameters, not genuine OEM values."""

    def parameter(value, source_id, evidence):
        return ParameterRecord(
            value=str(value),
            source_id=source_id,
            evidence=evidence,
            page="1",
        )

    panel = Component(
        component_id="TEST_PANEL",
        component_type="panel",
        parameters={
            "alpha_sc_a_per_c": parameter(
                0.001, "D1", "datasheet"
            ),
            "a_ref_v": parameter(
                1.0, model_source, model_evidence
            ),
            "i_l_ref_a": parameter(
                10.0, model_source, model_evidence
            ),
            "i_o_ref_a": parameter(
                1e-9, model_source, model_evidence
            ),
            "r_sh_ref_ohm": parameter(
                200.0, model_source, model_evidence
            ),
            "r_s_ohm": parameter(
                0.2, model_source, model_evidence
            ),
        },
    )

    inverter = Component(
        component_id="TEST_INVERTER",
        component_type="inverter",
        parameters={
            "rated_ac_w": parameter(
                50000, "D2", "datasheet"
            ),
            "eta_nominal_curve_parameter": parameter(
                0.96, model_source, model_evidence
            ),
        },
    )

    return panel, inverter


def test_filled_synthetic_coefficients_cannot_unlock_real_physics():

    panel, inverter = component_fixtures(
        model_evidence="synthetic_fixture_curve_fit",
    )

    report = assess_oem_readiness(panel, inverter)

    assert report.missing == ()
    assert not report.real_physics_ready
    assert "PANEL:a_ref_v" in report.unverified

    assert (
        "INVERTER:eta_nominal_curve_parameter"
        in report.unverified
    )

    assert (
        "UNVERIFIED_OR_SYNTHETIC_MODEL_PROVENANCE"
        in report.warnings
    )

    with pytest.raises(
        ValueError,
        match="unverified provenance",
    ):
        require_real_oem_model(panel, inverter)


@pytest.mark.parametrize(
    "evidence, source",
    [
        ("datasheet", "D3"),
        (
            "independently_validated_curve_fit",
            "synthetic_fixture",
        ),
        ("unverified_calibrated_fit", "LAB-A"),
    ],
)
def test_unreliable_model_sources_are_rejected(
    evidence,
    source,
):

    panel, inverter = component_fixtures(
        model_evidence=evidence,
        model_source=source,
    )

    result = assess_oem_readiness(panel, inverter)

    assert not result.real_physics_ready
    assert result.unverified


def test_explicit_model_fit_provenance_is_distinguished_from_missing():

    panel, inverter = component_fixtures(
        model_evidence="independently_validated_model_fit",
    )

    result = assess_oem_readiness(panel, inverter)

    assert not result.missing
    assert not result.unverified

    # Only validates declared evidence metadata.
    assert result.real_physics_ready


def test_missing_second_inverter_mppt_report_rolls_back(
    tmp_path,
):

    pipeline = build_integrated_demo_pipeline()

    weather = load_weather_intervals_csv(
        WEATHER
    )[1]

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    simulator.step(
        SolarIntervalInput(
            start_utc=weather.start_utc,
            end_utc=weather.end_utc,
            weather=weather.weather,
        )
    )

    original = simulator.records[0]

    assert len(original.inverter_results) == 2
    assert len(original.mppt_reports) == 2

    simulator.records[0] = replace(
        original,
        mppt_reports=(
            original.mppt_reports[0],
        ),
    )

    historian = SolarHistorian(
        tmp_path / "atomic.sqlite3"
    )

    with pytest.raises(
        ValueError,
        match="Missing MPPT report for inverter",
    ):
        historian.save_simulation(
            simulator,
            inverter_snapshot_payloads=(
                build_integrated_snapshots(pipeline)
            ),
        )

    assert historian.list_runs() == []

    with historian._connect() as db:

        for table in (
            "production_intervals",
            "ges_inverter_intervals",
            "ges_mppt_intervals",
            "ges_pq_intervals",
        ):
            count = db.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            assert count == 0


def test_missing_all_integrated_mppt_reports_rolls_back(
    tmp_path,
):

    pipeline = build_integrated_demo_pipeline()

    weather = load_weather_intervals_csv(
        WEATHER
    )[1]

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    simulator.step(
        SolarIntervalInput(
            start_utc=weather.start_utc,
            end_utc=weather.end_utc,
            weather=weather.weather,
        )
    )

    original = simulator.records[0]

    simulator.records[0] = replace(
        original,
        mppt_reports=(),
    )

    historian = SolarHistorian(
        tmp_path / "empty_integrated_mppt.sqlite3"
    )

    with pytest.raises(
        ValueError,
        match="Integrated GES interval missing MPPT",
    ):
        historian.save_simulation(
            simulator,
            inverter_snapshot_payloads=(
                build_integrated_snapshots(pipeline)
            ),
        )

    assert historian.list_runs() == []

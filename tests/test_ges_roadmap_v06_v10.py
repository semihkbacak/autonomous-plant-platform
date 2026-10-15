"""Focused v0.6-v1.0 tests; all equipment fixtures are synthetic."""
from __future__ import annotations

from dataclasses import replace
from math import isfinite

import numpy as np
import pytest
import pvlib

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
)

from simulator.solar.ges_v06_calibration import (
    IVSample,
    validate_iv_samples,
    fit_desoto_from_iv,
)

from simulator.solar.ges_v07_shading import (
    IrradianceGroup,
    calculate_shaded_string,
)

from simulator.solar.ges_v07_inverter import (
    InverterScreeningCurve,
)

from simulator.solar.ges_v08_supervisor import (
    GESSimulationSupervisor,
)

from simulator.solar.ges_v09_validation import (
    run_long_horizon,
)

from simulator.solar.pv_array import (
    synthetic_demo_module,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)


@pytest.fixture(scope="module")
def inputs():
    return make_stress_intervals(1)


def _synthetic_iv():

    m = synthetic_demo_module()
    samples = []

    conditions = [
        ("A", 450.0, 20.0),
        ("B", 850.0, 40.0),
        ("C", 1000.0, 25.0),
        ("D", 650.0, 30.0),
    ]

    for id_, ghi, temp in conditions:

        il, io, rs, rsh, a = (
            pvlib.pvsystem.calcparams_desoto(
                effective_irradiance=ghi,
                temp_cell=temp,
                alpha_sc=m.alpha_sc_a_per_c,
                a_ref=m.a_ref_v,
                I_L_ref=m.i_l_ref_a,
                I_o_ref=m.i_o_ref_a,
                R_sh_ref=m.r_sh_ref_ohm,
                R_s=m.r_s_ohm,
            )
        )

        voc = float(
            pvlib.pvsystem.singlediode(
                il, io, rs, rsh, a
            )["v_oc"]
        )

        for volt in np.linspace(
            0, voc * 0.96, 10
        ):

            amp = max(
                0.0,
                float(
                    pvlib.pvsystem.i_from_v(
                        volt, il, io, rs, rsh, a
                    )
                ),
            )

            samples.append(
                IVSample(
                    id_,
                    ghi,
                    temp,
                    float(volt),
                    amp,
                )
            )

    return samples


def test_v06_provisional_desoto_fit_with_curve_holdout():

    m = synthetic_demo_module()

    result = fit_desoto_from_iv(
        _synthetic_iv(),
        initial=m,
        provenance="SYNTHETIC_TEST_IV_GENERATOR",
        holdout_curve_id="D",
    )

    assert result.optimizer_success
    assert result.training_count == 30
    assert result.holdout_count == 10

    assert result.training_rmse_a < 1e-4
    assert result.holdout_rmse_a < 1e-4

    assert not result.oem_verified

    assert result.report()["status"] == (
        "PROVISIONAL_CURVE_FIT_NOT_OEM_VERIFIED"
    )


def test_v06_rejects_bad_dataset():

    values = _synthetic_iv()

    with pytest.raises(
        ValueError, match="Nonfinite"
    ):
        validate_iv_samples([
            replace(
                values[0],
                current_a=float("nan"),
            ),
            *values[1:],
        ])

    with pytest.raises(
        ValueError, match="three separate"
    ):
        validate_iv_samples(
            [
                v for v in values
                if v.curve_id == "A"
            ] * 4
        )


def test_v06_requires_source_provenance():

    with pytest.raises(
        ValueError, match="provenance"
    ):
        fit_desoto_from_iv(
            _synthetic_iv(),
            initial=synthetic_demo_module(),
            provenance="",
        )


def test_v07_shading_changes_curve_and_creates_multiple_maxima():

    m = synthetic_demo_module()

    uniform = calculate_shaded_string(
        m,
        (IrradianceGroup(10, 900, 30),),
        mppt_min_v=100,
        mppt_max_v=800,
    )

    shaded = calculate_shaded_string(
        m,
        (
            IrradianceGroup(5, 900, 30),
            IrradianceGroup(5, 200, 30),
        ),
        mppt_min_v=100,
        mppt_max_v=800,
    )

    assert (
        0 < shaded.global_mpp_w
        < uniform.global_mpp_w
    )

    assert shaded.local_peak_count >= 2

    assert (
        shaded.global_mpp_w
        >= shaded.mppt_window_mpp_w
    )


def test_v07_window_and_dark():

    m = synthetic_demo_module()

    dark = calculate_shaded_string(
        m,
        (IrradianceGroup(6, 0, 20),),
        mppt_min_v=100,
        mppt_max_v=200,
    )

    assert dark.global_mpp_w == 0

    restricted = calculate_shaded_string(
        m,
        (IrradianceGroup(10, 900, 30),),
        mppt_min_v=100,
        mppt_max_v=120,
    )

    assert restricted.limited_by_window

    with pytest.raises(ValueError):
        calculate_shaded_string(
            m,
            (IrradianceGroup(0, 900, 30),),
            mppt_min_v=100,
            mppt_max_v=200,
        )


def _curve(inverter_id, rating):

    return InverterScreeningCurve(
        inverter_id,
        rating,
        (
            (0, 0),
            (5, 0.92),
            (15, 0.97),
        ),
        (
            (-30, 1),
            (35, 1),
            (65, 0.65),
        ),
        "SYNTHETIC_TEST_CURVE_NOT_OEM",
    )


def test_v07_opt_in_pipeline_curve_changes_inverter_output(inputs):

    baseline = build_integrated_demo_pipeline()

    names = {
        asset.inverter.inverter_id:
            asset.inverter.rated_ac_kw
        for asset in baseline.assets
    }

    upgraded = IntegratedSolarPhysicsPipeline(
        baseline.site,
        baseline.assets,
        baseline.mppt_configs,
        inverter_curves={
            key: _curve(key, rating)
            for key, rating in names.items()
        },
    )

    weather = inputs[45].weather

    old = baseline.simulate(weather)
    new = upgraded.simulate(weather)

    assert len(new.mppt_reports) == len(
        old.mppt_reports
    )

    assert any(
        "USER_SUPPLIED_CURVE_NOT_OEM_CALIBRATED"
        in i.reasons
        for i in new.plant.inverter_results
    )

    assert new.plant.available_power_kw >= 0

    assert (
        new.plant.available_power_kw
        != pytest.approx(
            old.plant.available_power_kw
        )
    )


def test_v07_curve_mapping_must_match_nameplate():

    base = build_integrated_demo_pipeline()

    with pytest.raises(
        ValueError, match="Unknown inverter"
    ):
        IntegratedSolarPhysicsPipeline(
            base.site,
            base.assets,
            base.mppt_configs,
            inverter_curves={
                "WRONG": _curve("WRONG", 10)
            },
        )


def test_v08_supervisor_good_then_nonfinite_then_latched(inputs):

    supervisor = GESSimulationSupervisor()

    assert supervisor.inspect(
        inputs[0]
    ).allowed

    modified = replace(
        inputs[1],
        weather=replace(
            inputs[1].weather,
            wind_speed_m_s=float("nan"),
        ),
    )

    response = supervisor.inspect(modified)

    assert not response.allowed
    assert response.code == "TELEMETRY_NONFINITE"

    assert not supervisor.inspect(
        inputs[1]
    ).allowed

    with pytest.raises(PermissionError):
        supervisor.reset()

    supervisor.reset(
        operator_acknowledged=True
    )

    assert supervisor.inspect(
        inputs[0]
    ).allowed


def test_v08_supervisor_rejects_missing_interval_and_range(inputs):

    supervisor = GESSimulationSupervisor()

    assert supervisor.inspect(
        inputs[0]
    ).allowed

    result = supervisor.inspect(inputs[2])

    assert not result.allowed
    assert (
        result.code
        == "TELEMETRY_TIMESTAMP_INVALID"
    )

    supervisor.reset(
        operator_acknowledged=True
    )

    invalid = replace(
        inputs[0],
        weather=replace(
            inputs[0].weather,
            ambient_temperature_c=100.0,
        ),
    )

    assert supervisor.inspect(invalid).code == (
        "TELEMETRY_RANGE_INVALID"
    )


def test_v09_long_horizon_two_days_no_database():

    result = run_long_horizon(
        2,
        scenario="BASELINE_PQ8",
    )

    assert result.valid
    assert result.days == 2
    assert result.intervals == 192

    assert (
        isfinite(result.ac_energy_kwh)
        and result.ac_energy_kwh > 0
    )

    assert result.source_kind == (
        "SYNTHETIC_STRESS_NOT_FIELD_DATA"
    )


def test_v09_invalid_horizon():

    with pytest.raises(ValueError):
        run_long_horizon(366)


def test_v07_shaded_profile_integrates_without_changing_other_mppt(inputs):

    base = build_integrated_demo_pipeline()

    original = base.simulate(
        inputs[45].weather
    )

    pipeline = IntegratedSolarPhysicsPipeline(
        base.site,
        base.assets,
        base.mppt_configs,
        shading_profiles={
            "INV_1": {
                1: (
                    IrradianceGroup(5, 900, 30),
                    IrradianceGroup(5, 200, 30),
                ),
            },
        },
    )

    altered = pipeline.simulate(
        inputs[45].weather
    )

    channel = (
        altered.mppt_reports[0].dc.channels[0]
    )

    unchanged = (
        altered.mppt_reports[0].dc.channels[1]
    )

    assert channel.dc.model == (
        "APPROXIMATE_GROUP_BYPASS"
    )

    assert channel.offered_kw > 0

    assert unchanged.offered_kw == pytest.approx(
        original.mppt_reports[0]
        .dc.channels[1].offered_kw
    )

    assert (
        altered.plant.dispatched_power_kw >= 0
    )


def test_v07_shading_mismatch_fails_closed(inputs):

    base = build_integrated_demo_pipeline()

    pipeline = IntegratedSolarPhysicsPipeline(
        base.site,
        base.assets,
        base.mppt_configs,
        shading_profiles={
            "INV_1": {
                1: (
                    IrradianceGroup(2, 900, 30),
                ),
            },
        },
    )

    with pytest.raises(
        ValueError, match="module counts"
    ):
        pipeline.simulate(
            inputs[45].weather
        )


def test_v08_guarded_step_fails_closed_and_does_not_advance(inputs):

    class CrashSimulator:
        def step(self, item):
            raise RuntimeError(
                "simulation rejected"
            )

    supervisor = GESSimulationSupervisor()

    with pytest.raises(RuntimeError):
        supervisor.guarded_step(
            CrashSimulator(),
            inputs[0],
        )

    assert supervisor.last_end_utc is None

    assert supervisor.latched_fault == (
        "SIMULATION_STEP_FAILED"
    )

    with pytest.raises(
        ValueError, match="blocked"
    ):
        supervisor.guarded_step(
            CrashSimulator(),
            inputs[0],
        )
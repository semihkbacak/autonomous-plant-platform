
"""v1.0 software-release tests. All weather and curves here are SYNTHETIC."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from demo_ges_v05_scenarios import run_matrix
from ges_v10_release import annual_smoke
from simulator.solar.ges_v10_models import (
    InverterScreeningCurve,
)
from simulator.solar.ges_v10_quality import (
    audit_scenario_matrix,
    compare_power_csv,
)


@pytest.fixture(scope="module")
def sample_matrix(tmp_path_factory):
    folder = tmp_path_factory.mktemp("v10_sample")
    run_matrix(
        1,
        ["BASELINE_PQ8", "BASELINE_NO_Q"],
        folder,
    )
    return folder


def test_acceptance_partial_matrix_reconciles_without_inflating_pq(
    sample_matrix,
):
    result = audit_scenario_matrix(
        sample_matrix,
        require_full=False,
    )
    assert result.passed, result.issues
    assert result.details["db_rows"] == {
        "production_intervals": 192,
        "ges_inverter_intervals": 384,
        "ges_mppt_intervals": 768,
        "ges_pq_intervals": 192,
    }
    assert (
        result.details["oem_calibration"]
        == "NOT_VERIFIED"
    )


def test_partial_run_cannot_claim_full_release(
    sample_matrix,
):
    result = audit_scenario_matrix(
        sample_matrix
    )
    assert not result.passed
    assert "EXPECTED_CASES" in result.issues


def test_pq_row_deletion_detected(
    sample_matrix,
    tmp_path,
):
    import shutil

    out = tmp_path / "broken"
    shutil.copytree(sample_matrix, out)

    with sqlite3.connect(
        out / "historian.sqlite3"
    ) as db:
        db.execute(
            "DELETE FROM ges_pq_intervals "
            "WHERE rowid=(SELECT rowid "
            "FROM ges_pq_intervals LIMIT 1)"
        )

    result = audit_scenario_matrix(
        out,
        require_full=False,
    )

    assert not result.passed
    assert "PQ_ROWS" in result.issues


def test_missing_archive_fails_closed(tmp_path):
    result = audit_scenario_matrix(tmp_path)
    assert not result.passed
    assert result.issues == ("MISSING_ARTIFACTS",)


def test_curve_interpolation_and_separate_losses():
    curve = InverterScreeningCurve(
        "DEMO",
        10.0,
        (
            (0.0, 0.0),
            (5.0, 0.95),
            (15.0, 0.97),
        ),
        (
            (0.0, 1.0),
            (40.0, 1.0),
            (70.0, 0.5),
        ),
        "SYNTHETIC_TEST_ASSUMPTION_NOT_OEM",
    )

    value = curve.screen(12.0, 55.0)

    assert value["ac_kw"] == pytest.approx(7.5)
    assert value["clipped_kw"] > 0
    assert (
        value["mode"]
        == "SUPPLIED_CURVE_SCREENING_NOT_OEM_CALIBRATION"
    )


def test_curve_rejects_extrapolation_and_invalid_fractions():
    with pytest.raises(ValueError):
        InverterScreeningCurve(
            "A",
            10,
            ((0, 0.2), (4, 1.2)),
            ((0, 1), (70, .8)),
            "synthetic",
        )

    with pytest.raises(ValueError):
        InverterScreeningCurve(
            "A",
            10,
            ((0, 0.2), (4, .9)),
            ((0, 1), (70, .8)),
            "synthetic",
        ).screen(5, 20)


def _write_benchmark(
    path: Path,
    *,
    duplicates=False,
):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "timestamp_utc",
                "predicted_kw",
                "measured_kw",
            )
        )
        writer.writerow(
            (
                "2026-06-21T00:00:00+00:00",
                2,
                1,
            )
        )
        writer.writerow(
            (
                "2026-06-21T00:00:00+00:00"
                if duplicates
                else "2026-06-21T00:15:00+00:00",
                4,
                3,
            )
        )


def test_benchmark_mae_rmse_bias_and_provenance(
    tmp_path,
):
    path = tmp_path / "benchmark.csv"
    _write_benchmark(path)

    metric = compare_power_csv(path)

    assert metric["mae_kw"] == pytest.approx(1)
    assert metric["rmse_kw"] == pytest.approx(1)
    assert metric["bias_kw"] == pytest.approx(1)
    assert metric["energy_error_pct"] == pytest.approx(50)
    assert metric["site_validated"] is False


def test_benchmark_rejects_duplicate_time(
    tmp_path,
):
    path = tmp_path / "bad.csv"
    _write_benchmark(path, duplicates=True)

    with pytest.raises(
        ValueError,
        match="Noncontiguous",
    ):
        compare_power_csv(path)


def test_benchmark_rejects_nonfinite_and_naive_timestamps(
    tmp_path,
):
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp_utc,predicted_kw,measured_kw\n"
        "2026-06-21T00:00:00,1,1\n"
        "2026-06-21T00:15:00,NaN,1\n"
    )

    with pytest.raises(
        ValueError,
        match="UTC",
    ):
        compare_power_csv(path)


def test_short_annual_smoke_has_96_intervals():
    result = annual_smoke(
        1,
        "BASELINE_PQ8",
    )

    assert result["intervals"] == 96
    assert result["energy_kwh"] > 0
    assert (
        result["scope"]
        == "SYNTHETIC_NOT_FIELD_VALIDATION"
    )


def test_annual_invalid_horizon_is_rejected():
    with pytest.raises(ValueError):
        annual_smoke(
            366,
            "BASELINE_PQ8",
        )

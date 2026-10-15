
from pathlib import Path

import pytest

from simulator.solar.component_catalog import (
    load_component_catalog,
)
from simulator.solar.oem_design_review import (
    MPPTAssignment,
    review_oem_design,
)


CSV = (
    Path(__file__).resolve().parents[1]
    / "data/solar/reference/ges_component_parameters.csv"
)


@pytest.fixture(scope="module")
def catalog():
    return load_component_catalog(CSV)


def review(
    catalog,
    inverter="SMA_STP50_40",
    entries=None,
    **changes,
):
    if entries is None:
        entries = (
            MPPTAssignment(
                1, "TRINA_TSM445_NEG9R28", 15, 1
            ),
        )

    return review_oem_design(
        catalog,
        inverter_id=inverter,
        assignments=entries,
        min_cell_temperature_c=-10,
        max_cell_temperature_c=70,
        **changes,
    )


def test_sma_one_string_is_preliminarily_ok(catalog):
    r = review(catalog)

    assert r.passes_preliminary_checks
    assert not r.approved_for_installation

    assert r.channels[0].connected_stc_kw == pytest.approx(
        6.675
    )

    assert r.channels[0].string_voc_cold_v == pytest.approx(
        855.276
    )


def test_sma_two_strings_current_limit(catalog):
    r = review(
        catalog,
        entries=(
            MPPTAssignment(
                1, "TRINA_TSM445_NEG9R28", 15, 2
            ),
        ),
    )

    assert (
        "MPPT_1:MPPT_OPERATING_CURRENT_EXCEEDED"
        in r.issues
    )


def test_sungrow_jinko_two_strings_current_limit_and_connector(
    catalog,
):
    r = review(
        catalog,
        inverter="SUNGROW_SG110CX_V152",
        entries=(
            MPPTAssignment(
                1, "JINKO_JKM585N72HL4V", 18, 2
            ),
        ),
    )

    assert (
        "MPPT_1:MPPT_OPERATING_CURRENT_EXCEEDED"
        in r.issues
    )

    assert (
        "MPPT_1:OEM_CONNECTOR_REVIEW_ABOVE_1000V"
        in r.warnings
    )

    assert "RATED_ACTIVE_POWER_UNAVAILABLE" in r.warnings


def test_sma_cold_voltage_exceeded(catalog):
    r = review(
        catalog,
        entries=(
            MPPTAssignment(
                1, "TRINA_TSM445_NEG9R28", 20, 1
            ),
        ),
    )

    assert (
        "MPPT_1:INVERTER_MAX_DC_VOLTAGE_EXCEEDED"
        in r.issues
    )


def test_duplicate_mppt_is_rejected(catalog):
    duplicate = (
        MPPTAssignment(
            1, "TRINA_TSM445_NEG9R28", 15, 1
        ),
    ) * 2

    with pytest.raises(ValueError, match="Duplicate MPPT"):
        review(catalog, entries=duplicate)


def test_excess_mppt_index_is_rejected(catalog):
    with pytest.raises(ValueError, match="MPPT index"):
        review(
            catalog,
            entries=(
                MPPTAssignment(
                    7, "TRINA_TSM445_NEG9R28", 15, 1
                ),
            ),
        )


def test_sma_total_generator_rating(catalog):
    entries = tuple(
        MPPTAssignment(
            n, "TRINA_TSM445_NEG9R28", 15, 2
        )
        for n in range(1, 7)
    )

    r = review(catalog, entries=entries)

    assert r.total_connected_stc_kw == pytest.approx(
        80.1
    )

    assert (
        "TOTAL_PV_STC_EXCEEDS_GENERATOR_LIMIT"
        in r.issues
    )


def test_sungrow_generator_rating_unknown(catalog):
    r = review(
        catalog,
        inverter="SUNGROW_SG110CX_V152",
        entries=(
            MPPTAssignment(
                1, "JINKO_JKM585N72HL4V", 12, 1
            ),
        ),
    )

    assert r.max_generator_stc_kw is None

    assert (
        "MAX_GENERATOR_STC_RATING_UNAVAILABLE"
        in r.warnings
    )


def test_sungrow_50c_pq_limit(catalog):
    r = review(
        catalog,
        inverter="SUNGROW_SG110CX_V152",
        entries=(
            MPPTAssignment(
                1, "JINKO_JKM585N72HL4V", 12, 1
            ),
        ),
        ambient_temperature_c=50,
        requested_active_kw=90,
        requested_reactive_kvar=60,
    )

    assert r.ac_screen.applied_kva_limit == pytest.approx(
        100
    )

    assert r.ac_screen.max_active_kw == pytest.approx(
        80
    )

    assert (
        "AC_REQUEST_OUTSIDE_SIMPLIFIED_PQ_LIMIT"
        in r.issues
    )


def test_sungrow_45c_reference_point(catalog):
    r = review(
        catalog,
        inverter="SUNGROW_SG110CX_V152",
        entries=(
            MPPTAssignment(
                1, "JINKO_JKM585N72HL4V", 12, 1
            ),
        ),
        ambient_temperature_c=45,
        requested_active_kw=90,
        requested_reactive_kvar=60,
    )

    assert r.ac_screen.applied_kva_limit == 110
    assert r.ac_screen.request_is_feasible


def test_sungrow_48c_does_not_interpolate(catalog):
    r = review(
        catalog,
        inverter="SUNGROW_SG110CX_V152",
        entries=(
            MPPTAssignment(
                1, "JINKO_JKM585N72HL4V", 12, 1
            ),
        ),
        ambient_temperature_c=48,
        requested_active_kw=90,
        requested_reactive_kvar=60,
    )

    assert "THERMAL_CURVE_NOT_AVAILABLE" in r.warnings

    assert r.ac_screen.applied_kva_limit == 110

    assert (
        "THERMAL_CAPABILITY_NOT_VERIFIED"
        in r.warnings
    )


def test_sma_ac_active_limit(catalog):
    r = review(
        catalog,
        requested_active_kw=55,
        requested_reactive_kvar=0,
    )

    assert "REQUEST_EXCEEDS_RATED_ACTIVE_POWER" in r.issues
    assert r.ac_screen.max_active_kw == 50


def test_incomplete_ac_request_rejected(catalog):
    with pytest.raises(
        ValueError,
        match="Both active and reactive",
    ):
        review(
            catalog,
            requested_active_kw=10,
        )


def test_bad_cell_temperature_rejected(catalog):
    with pytest.raises(ValueError):
        review_oem_design(
            catalog,
            inverter_id="SMA_STP50_40",
            assignments=[
                MPPTAssignment(
                    1, "TRINA_TSM445_NEG9R28", 15, 1
                )
            ],
            min_cell_temperature_c=80,
            max_cell_temperature_c=-10,
        )


def test_missing_panel_rejected(catalog):
    with pytest.raises(ValueError, match="Panel not found"):
        review(
            catalog,
            entries=(
                MPPTAssignment(
                    1, "NO_SUCH_PANEL", 15, 1
                ),
            ),
        )

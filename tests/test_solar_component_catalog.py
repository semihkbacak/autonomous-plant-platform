
from pathlib import Path
from simulator.solar.component_catalog import check_string_temperature_voltage
import pytest

from simulator.solar.component_catalog import (
    load_component_catalog,
    check_mppt_at_stc,
)

# ============================================================
# TEMPERATURE VOLTAGE TESTS
# ============================================================


def test_datasheet_voc_temperature_coefficients(devices):
    trina = devices["TRINA_TSM445_NEG9R28"]
    jinko = devices["JINKO_JKM585N72HL4V"]

    assert trina.number("beta_voc_per_C") == pytest.approx(
        -0.0024
    )

    assert jinko.number("beta_voc_per_C") == pytest.approx(
        -0.0025
    )


def test_trina_15_modules_cold_voltage(devices):
    result = check_string_temperature_voltage(
        panel=devices["TRINA_TSM445_NEG9R28"],
        inverter=devices["SMA_STP50_40"],
        modules_per_string=15,
        min_cell_temperature_c=-10,
        max_cell_temperature_c=70,
    )

    assert result.cold_string_voc_v == pytest.approx(
        855.276
    )

    assert result.within_dc_voltage_limits

    assert (
        "MPPT_TEMPERATURE_WINDOW_NOT_VERIFIED"
        in result.warnings
    )


def test_trina_20_modules_exceed_sma_limit(devices):
    result = check_string_temperature_voltage(
        panel=devices["TRINA_TSM445_NEG9R28"],
        inverter=devices["SMA_STP50_40"],
        modules_per_string=20,
        min_cell_temperature_c=-10,
        max_cell_temperature_c=70,
    )

    assert result.cold_string_voc_v == pytest.approx(
        1140.368
    )

    assert not result.within_dc_voltage_limits

    assert (
        "INVERTER_MAX_DC_VOLTAGE_EXCEEDED"
        in result.issues
    )


def test_jinko_sungrow_connector_review(devices):
    result = check_string_temperature_voltage(
        panel=devices["JINKO_JKM585N72HL4V"],
        inverter=devices["SUNGROW_SG110CX_V152"],
        modules_per_string=18,
        min_cell_temperature_c=-10,
        max_cell_temperature_c=70,
    )

    assert result.cold_string_voc_v == pytest.approx(
        1001.457
    )

    assert result.within_dc_voltage_limits

    assert (
        "OEM_CONNECTOR_REVIEW_ABOVE_1000V"
        in result.warnings
    )


def test_reversed_temperature_range_is_rejected(devices):
    with pytest.raises(ValueError):
        check_string_temperature_voltage(
            panel=devices["TRINA_TSM445_NEG9R28"],
            inverter=devices["SMA_STP50_40"],
            modules_per_string=15,
            min_cell_temperature_c=70,
            max_cell_temperature_c=-10,
        )


def test_invalid_temperature_and_count_are_rejected(devices):
    panel = devices["TRINA_TSM445_NEG9R28"]
    inverter = devices["SMA_STP50_40"]

    for invalid_temp in (
        float("nan"),
        float("inf"),
        -300.0,
    ):
        with pytest.raises(ValueError):
            check_string_temperature_voltage(
                panel=panel,
                inverter=inverter,
                modules_per_string=15,
                min_cell_temperature_c=invalid_temp,
                max_cell_temperature_c=70,
            )

    with pytest.raises(ValueError):
        check_string_temperature_voltage(
            panel=panel,
            inverter=inverter,
            modules_per_string=0,
            min_cell_temperature_c=-10,
            max_cell_temperature_c=70,
        )



CSV_FILE = (
    Path(__file__).resolve().parents[1]
    / "data/solar/reference/ges_component_parameters.csv"
)


@pytest.fixture
def devices():
    return load_component_catalog(CSV_FILE)


def test_four_components_loaded(devices):
    assert len(devices) == 4

    assert devices["TRINA_TSM445_NEG9R28"].number(
        "p_stc_w"
    ) == 445

    assert devices["JINKO_JKM585N72HL4V"].number(
        "p_stc_w"
    ) == 585


def test_unknown_efficiency_remains_none(devices):
    for device_id in (
        "SMA_STP50_40",
        "SUNGROW_SG110CX_V152",
    ):
        assert devices[device_id].number(
            "eta_nominal_curve_parameter",
            required=False,
        ) is None


def test_trina_two_strings_exceed_sma_current(devices):
    result = check_mppt_at_stc(
        panel=devices["TRINA_TSM445_NEG9R28"],
        inverter=devices["SMA_STP50_40"],
        modules_per_string=15,
        strings_per_mppt=2,
    )

    assert result.mppt_imp_a == pytest.approx(20.10)

    assert (
        "MPPT_OPERATING_CURRENT_EXCEEDED"
        in result.issues
    )


def test_jinko_two_strings_exceed_sungrow_current(devices):
    result = check_mppt_at_stc(
        panel=devices["JINKO_JKM585N72HL4V"],
        inverter=devices["SUNGROW_SG110CX_V152"],
        modules_per_string=18,
        strings_per_mppt=2,
    )

    assert result.mppt_imp_a == pytest.approx(27.52)

    assert (
        "MPPT_OPERATING_CURRENT_EXCEEDED"
        in result.issues
    )


def test_trina_single_string_passes_stc_screening(devices):
    result = check_mppt_at_stc(
        panel=devices["TRINA_TSM445_NEG9R28"],
        inverter=devices["SMA_STP50_40"],
        modules_per_string=15,
        strings_per_mppt=1,
    )

    assert result.string_vmp_v == pytest.approx(664.5)
    assert result.string_voc_v == pytest.approx(789.0)
    assert result.passes_stc_checks


def test_excess_dc_voltage_detected(devices):
    result = check_mppt_at_stc(
        panel=devices["TRINA_TSM445_NEG9R28"],
        inverter=devices["SMA_STP50_40"],
        modules_per_string=20,
        strings_per_mppt=1,
    )

    assert (
        "INVERTER_DC_OVERVOLTAGE_AT_STC"
        in result.issues
    )


import csv
import math

from collections import defaultdict
from pathlib import Path

import pytest

from pvlib.pvsystem import pvwatts_dc


# ============================================================
# PROJECT DIRECTORIES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REFERENCE_DIR = (
    PROJECT_ROOT / "data" / "solar" / "reference"
)


# ============================================================
# CSV FILE READER
# ============================================================

def read_csv(filename: str) -> list[dict]:
    """
    Read a CSV file from the reference directory.
    """

    path = REFERENCE_DIR / filename

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        return list(reader)


# ============================================================
# REAL SOLAR PANEL PARAMETERS
# ============================================================

def load_panel_parameters() -> dict:
    """
    Extract verified datasheet parameters.

    PVWatts needs:
    - STC rated power
    - temperature coefficient
    """

    rows = read_csv(
        "ges_component_parameters.csv"
    )

    panels = defaultdict(dict)

    for row in rows:

        if row["component_type"] != "panel":
            continue

        parameter = row["parameter"]

        if parameter not in (
            "p_stc_w",
            "gamma_p_per_C",
        ):
            continue

        # Check parameter source.
        assert row["evidence"] == "datasheet"

        assert row["source_id"] in {
            "D1",
            "D2",
        }

        panel_id = row["component_id"]

        panels[panel_id][parameter] = float(
            row["value"]
        )

        panels[panel_id]["source_id"] = (
            row["source_id"]
        )

    for panel in panels.values():

        assert panel["p_stc_w"] > 0

        assert (
            -0.01 < panel["gamma_p_per_C"] < 0
        )

    return dict(panels)


# ============================================================
# MANUAL PVWATTS DC CALCULATION
# ============================================================

def manual_pvwatts_dc(
    irradiance: float,
    temperature: float,
    p_stc: float,
    gamma: float,
) -> float:
    """
    PVWatts DC reference equation.

    irradiance: W/m2
    temperature: degrees Celsius
    p_stc: W
    gamma: 1/C

    Output:
        DC power in watts
    """

    values = (
        irradiance,
        temperature,
        p_stc,
        gamma,
    )

    assert all(
        math.isfinite(value)
        for value in values
    )

    assert irradiance >= 0

    power = (
        p_stc
        * (irradiance / 1000.0)
        * (1.0 + gamma * (temperature - 25.0))
    )

    return power


# ============================================================
# TEST 1: FILE CONTENT
# ============================================================

def test_reference_files_are_complete():

    components = read_csv(
        "ges_component_parameters.csv"
    )

    benchmarks = read_csv(
        "ges_benchmark_results.csv"
    )

    assert len(components) == 76

    assert len(benchmarks) == 40


# ============================================================
# TEST 2: PANEL PARAMETERS
# ============================================================

def test_two_panel_parameter_sets():

    panels = load_panel_parameters()

    assert len(panels) == 2

    trina = panels["TRINA_TSM445_NEG9R28"]

    jinko = panels["JINKO_JKM585N72HL4V"]

    assert trina["p_stc_w"] == 445.0

    assert jinko["p_stc_w"] == 585.0

    assert trina["gamma_p_per_C"] == -0.003

    assert jinko["gamma_p_per_C"] == -0.0029


# ============================================================
# TEST 3: ALL 40 BENCHMARK CALCULATIONS
# ============================================================

def test_all_40_reference_calculations():

    panels = load_panel_parameters()

    rows = read_csv(
        "ges_benchmark_results.csv"
    )

    checked = 0

    for row in rows:

        panel = panels[row["module_id"]]

        assert (
            row["source_id"]
            == panel["source_id"]
        )

        irradiance = float(
            row["effective_irradiance_Wm2"]
        )

        temperature = float(
            row["temp_cell_C"]
        )

        p_stc = panel["p_stc_w"]

        gamma = panel["gamma_p_per_C"]

        # Our independent formula.
        manual_result = manual_pvwatts_dc(
            irradiance,
            temperature,
            p_stc,
            gamma,
        )

        # Library reference calculation.
        pvlib_result = float(
            pvwatts_dc(
                irradiance,
                temperature,
                p_stc,
                gamma,
            )
        )

        # Teammate's recorded results.
        expected_manual = float(
            row["simple_dc_W"]
        )

        expected_pvlib = float(
            row["pvlib_pvwatts_dc_W"]
        )

        expected_difference = float(
            row["difference_W"]
        )

        assert manual_result == pytest.approx(
            expected_manual,
            rel=0,
            abs=1e-6,
        )

        assert pvlib_result == pytest.approx(
            expected_pvlib,
            rel=0,
            abs=1e-6,
        )

        assert (
            pvlib_result - manual_result
        ) == pytest.approx(
            expected_difference,
            rel=0,
            abs=1e-6,
        )

        checked += 1

    assert checked == 40


# ============================================================
# TEST 4: TEMPERATURE EFFECT
# ============================================================

def test_stc_and_temperature_effect():

    panels = load_panel_parameters()

    for panel in panels.values():

        rated_power = panel["p_stc_w"]

        gamma = panel["gamma_p_per_C"]

        power_25 = manual_pvwatts_dc(
            1000,
            25,
            rated_power,
            gamma,
        )

        power_45 = manual_pvwatts_dc(
            1000,
            45,
            rated_power,
            gamma,
        )

        assert power_25 == pytest.approx(
            rated_power
        )

        assert power_45 < power_25


# ============================================================
# TEST 5: NIGHT PRODUCTION
# ============================================================

def test_zero_irradiance_gives_zero_dc():

    panels = load_panel_parameters()

    for panel in panels.values():

        power = manual_pvwatts_dc(
            irradiance=0,
            temperature=25,
            p_stc=panel["p_stc_w"],
            gamma=panel["gamma_p_per_C"],
        )

        assert power == 0


# ============================================================
# TEST 6: UNKNOWN INVERTER EFFICIENCY
# ============================================================

def test_unknown_inverter_efficiency_stays_unknown():
    """
    Maximum efficiency must not silently
    replace nominal efficiency.
    """

    rows = read_csv(
        "ges_component_parameters.csv"
    )

    unknown_values = [
        row
        for row in rows
        if (
            row["component_type"] == "inverter"
            and row["parameter"]
            == "eta_nominal_curve_parameter"
        )
    ]

    assert len(unknown_values) == 2

    assert all(
        row["value"] == ""
        for row in unknown_values
    )

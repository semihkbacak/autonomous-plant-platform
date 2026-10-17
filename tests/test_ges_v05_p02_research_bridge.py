
"""P02: OEM research provenance isolation and read-only STC screening."""

from pathlib import Path

import pytest

from simulator.solar.oem_research_bridge import (
    load_researched_oem_catalog,
    screen_researched_string,
)

RESEARCH_ZIP = Path(__file__).resolve().parents[1] / "ges_oem_research.zip"


@pytest.fixture(scope="module")
def catalog():
    if not RESEARCH_ZIP.is_file():
        pytest.skip('Optional private research archive not shipped in public source distribution')
    return load_researched_oem_catalog(RESEARCH_ZIP)


def review(catalog, panel, inverter, *, modules=15, strings=1):
    return screen_researched_string(
        catalog, panel_id=panel, inverter_id=inverter,
        modules_per_string=modules, strings_per_mppt=strings,
        min_cell_temperature_c=-10, max_cell_temperature_c=70,
    )


def test_declared_sources_partitioned_and_retain_unknowns(catalog):
    assert len(catalog.components) == 4
    assert len(catalog.parameters) == 158
    assert catalog.accepted_count == 111
    assert catalog.quarantined_count == 47
    jinko = catalog.components["JINKO_JKM585N72HL4V"]
    assert jinko.number("max_system_v", required=False) is None
    assert jinko.number("a_ref_v", required=False) is None


def test_unknown_or_conditional_parameters_are_not_invented(catalog):
    trina = catalog.components["TRINA_TSM445_NEG9R28"]
    assert trina.number("alpha_sc_a_per_c", required=False) is None
    assert trina.number("p_stc_w") == 445
    assert trina.number("gamma_p_per_C") == pytest.approx(-0.003)


def test_conflicting_document_scope_requires_review(catalog):
    sma = catalog.components["SMA_STP50_40"]
    assert sma.number("eta_max_pct", required=False) is None
    assert not catalog.parameters[("SMA_STP50_40", "eta_max_pct")].accepted


def test_trina_sma_one_string_stc_screen(catalog):
    result = review(catalog, "TRINA_TSM445_NEG9R28", "SMA_STP50_40")
    assert result.screening_complete
    assert result.passes_screening
    assert result.stc.string_vmp_v == pytest.approx(664.5)
    assert not result.physics.real_physics_ready


def test_trina_sma_two_strings_exceed_mppt_current(catalog):
    result = review(catalog, "TRINA_TSM445_NEG9R28", "SMA_STP50_40", strings=2)
    assert result.screening_complete
    assert not result.passes_screening
    assert "MPPT_OPERATING_CURRENT_EXCEEDED" in result.stc.issues


def test_jinko_unknown_system_voltage_blocks_completeness(catalog):
    result = review(catalog, "JINKO_JKM585N72HL4V", "SUNGROW_SG110CX_V152", modules=18)
    assert "PANEL:max_system_v" in result.missing
    assert result.stc is None
    assert not result.screening_complete
    assert not result.passes_screening


def test_bad_temperature_rejected_even_with_unknown_source(catalog):
    with pytest.raises(ValueError, match="temperature"):
        screen_researched_string(
            catalog, panel_id="JINKO_JKM585N72HL4V",
            inverter_id="SUNGROW_SG110CX_V152",
            modules_per_string=18, strings_per_mppt=1,
            min_cell_temperature_c=float("nan"), max_cell_temperature_c=70,
        )


def test_repository_catalog_not_mutated(catalog):
    assert catalog.catalog_sha256
    assert len(catalog.catalog_sha256) == 64
    assert "SMA_STP50_40" in catalog.components

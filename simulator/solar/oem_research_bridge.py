
"""Read-only bridge for the GES OEM research delivery.

This module imports the research package's *declared* provenance. It does
NOT independently authenticate OEM datasheets, calibrate De Soto or inverter
curves, modify the live catalog, or authorize installation/OT control.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import zipfile

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from simulator.solar.component_catalog import (
    Component,
    ParameterRecord,
    STCCheck,
    TemperatureVoltageCheck,
    check_mppt_at_stc,
    check_string_temperature_voltage,
)
from simulator.solar.oem_model_readiness import (
    OEMReadiness,
    assess_oem_readiness,
)

CATALOG_SUFFIX = (
    "01_oem_parameter_catalog/ges_component_parameters_proposed.csv"
)
REQUIRED_COLUMNS = frozenset({
    "component_id", "component_type", "parameter", "value",
    "source_id", "evidence", "value_type", "verification_status",
    "source_document", "document_revision", "page_number", "source_url",
})
SELECTED_VALUE_TYPES = frozenset({"oem_published", "derived_from_oem"})
SELECTED_STATUS = "verified_selected_document"


@dataclass(frozen=True)
class ResearchParameter:
    component_id: str
    parameter: str
    value_type: str
    verification_status: str
    source_document: str
    document_revision: str
    page_number: str
    source_url: str
    accepted: bool
    reason: str


@dataclass(frozen=True)
class ResearchCatalog:
    components: dict[str, Component]
    parameters: dict[tuple[str, str], ResearchParameter]
    catalog_sha256: str
    accepted_count: int
    quarantined_count: int


@dataclass(frozen=True)
class ResearchStringScreen:
    missing: tuple[str, ...]
    stc: STCCheck | None
    temperature: TemperatureVoltageCheck | None
    physics: OEMReadiness

    @property
    def screening_complete(self) -> bool:
        return not self.missing and self.stc is not None and self.temperature is not None

    @property
    def passes_screening(self) -> bool:
        return (
            self.screening_complete
            and self.stc.passes_stc_checks
            and self.temperature.within_dc_voltage_limits
        )


def _has_traceable_source(row: dict[str, str]) -> bool:
    url = urlsplit(row["source_url"].strip())
    return bool(
        url.scheme == "https"
        and url.hostname
        and row["source_document"].strip()
        and row["document_revision"].strip()
        and row["page_number"].strip()
        and row["source_id"].strip()
        and row["evidence"].strip()
    )


def load_researched_oem_catalog(zip_path: str | Path) -> ResearchCatalog:
    """Stage declared OEM values without changing the project's original CSV.

    Unavailable, conditionally derived or scope-conflicted values are kept
    explicitly unknown (ParameterRecord.value=None), never inferred.
    """
    with zipfile.ZipFile(zip_path) as archive:
        matches = [
            name for name in archive.namelist()
            if name.endswith(CATALOG_SUFFIX) and not name.endswith("/")
        ]
        if len(matches) != 1:
            raise ValueError("Expected exactly one OEM research parameter catalog")
        info = archive.getinfo(matches[0])
        if info.file_size > 5_000_000:
            raise ValueError("OEM parameter catalog unexpectedly large")
        raw = archive.read(info)

    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not REQUIRED_COLUMNS.issubset(reader.fieldnames or ()):
        raise ValueError("OEM catalog missing required provenance columns")

    grouped: dict[str, dict[str, object]] = {}
    metadata: dict[tuple[str, str], ResearchParameter] = {}
    accepted_count = 0
    quarantined_count = 0

    for row in reader:
        if None in row:
            raise ValueError("Malformed OEM CSV row")
        component_id = row["component_id"].strip()
        component_type = row["component_type"].strip()
        name = row["parameter"].strip()
        if not component_id or not name or component_type not in {"panel", "inverter"}:
            raise ValueError("Invalid OEM component identity")
        key = (component_id, name)
        if key in metadata:
            raise ValueError(f"Duplicate OEM parameter: {component_id}/{name}")

        if component_id not in grouped:
            grouped[component_id] = {"type": component_type, "parameters": {}}
        if grouped[component_id]["type"] != component_type:
            raise ValueError(f"Conflicting component types: {component_id}")

        value_type = row["value_type"].strip()
        status = row["verification_status"].strip()
        value = row["value"].strip()
        if not value:
            reason = "missing_value"
        elif value_type not in SELECTED_VALUE_TYPES:
            reason = "not_a_selected_oem_value"
        elif status != SELECTED_STATUS:
            reason = "status_requires_review"
        elif not _has_traceable_source(row):
            reason = "insufficient_source_trace"
        else:
            reason = "accepted_from_research_metadata"

        accepted = reason == "accepted_from_research_metadata"
        if accepted:
            accepted_count += 1
        else:
            quarantined_count += 1

        parameters = grouped[component_id]["parameters"]
        assert isinstance(parameters, dict)
        parameters[name] = ParameterRecord(
            value=value if accepted else None,
            source_id=row["source_id"].strip() or "UNKNOWN",
            evidence=(row["evidence"].strip() if accepted else f"quarantined:{reason}"),
            page=row["page_number"].strip(),
        )
        metadata[key] = ResearchParameter(
            component_id=component_id,
            parameter=name,
            value_type=value_type,
            verification_status=status,
            source_document=row["source_document"].strip(),
            document_revision=row["document_revision"].strip(),
            page_number=row["page_number"].strip(),
            source_url=row["source_url"].strip(),
            accepted=accepted,
            reason=reason,
        )

    if not metadata:
        raise ValueError("Empty OEM research catalog")

    components = {
        component_id: Component(
            component_id=component_id,
            component_type=str(item["type"]),
            parameters=item["parameters"],
        )
        for component_id, item in grouped.items()
    }
    return ResearchCatalog(
        components=components,
        parameters=metadata,
        catalog_sha256=hashlib.sha256(raw).hexdigest(),
        accepted_count=accepted_count,
        quarantined_count=quarantined_count,
    )


def screen_researched_string(
    catalog: ResearchCatalog,
    *,
    panel_id: str,
    inverter_id: str,
    modules_per_string: int,
    strings_per_mppt: int,
    min_cell_temperature_c: float,
    max_cell_temperature_c: float,
) -> ResearchStringScreen:
    """STC/cold-Voc screening only; NOT a full energy model or design approval."""
    if type(modules_per_string) is not int or modules_per_string <= 0:
        raise ValueError("modules_per_string must be a positive integer")
    if type(strings_per_mppt) is not int or strings_per_mppt <= 0:
        raise ValueError("strings_per_mppt must be a positive integer")

    for value in (min_cell_temperature_c, max_cell_temperature_c):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= -273.15):
            raise ValueError("Invalid cell temperature")
    if min_cell_temperature_c > max_cell_temperature_c:
        raise ValueError("Minimum cell temperature exceeds maximum")

    panel = catalog.components[panel_id]
    inverter = catalog.components[inverter_id]
    physics = assess_oem_readiness(panel, inverter)

    panel_needed = (
        "v_mp_v", "v_oc_v", "i_mp_a", "i_sc_a", "max_system_v",
        "beta_voc_per_C",
    )
    inverter_needed = (
        "strings_per_mppt", "mppt_min_v", "mppt_max_v", "max_dc_v",
        "max_operating_current_per_mppt_a",
        "max_short_circuit_current_per_mppt_a",
    )
    missing = tuple(
        [f"PANEL:{name}" for name in panel_needed
         if panel.number(name, required=False) is None]
        + [f"INVERTER:{name}" for name in inverter_needed
           if inverter.number(name, required=False) is None]
    )
    if missing:
        return ResearchStringScreen(
            missing=missing, stc=None, temperature=None, physics=physics
        )

    stc = check_mppt_at_stc(
        panel, inverter, modules_per_string, strings_per_mppt
    )
    temperature = check_string_temperature_voltage(
        panel, inverter, modules_per_string,
        min_cell_temperature_c, max_cell_temperature_c,
    )
    return ResearchStringScreen(
        missing=(), stc=stc, temperature=temperature, physics=physics
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only OEM STC screening")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--panel", default="TRINA_TSM445_NEG9R28")
    parser.add_argument("--inverter", default="SMA_STP50_40")
    parser.add_argument("--modules", type=int, default=15)
    parser.add_argument("--strings", type=int, default=1)
    parser.add_argument("--min-cell", type=float, default=-10.0)
    parser.add_argument("--max-cell", type=float, default=70.0)
    args = parser.parse_args()
    catalog = load_researched_oem_catalog(args.zip)
    result = screen_researched_string(
        catalog, panel_id=args.panel, inverter_id=args.inverter,
        modules_per_string=args.modules, strings_per_mppt=args.strings,
        min_cell_temperature_c=args.min_cell, max_cell_temperature_c=args.max_cell,
    )
    print(json.dumps({
        "catalog_sha256": catalog.catalog_sha256,
        "accepted_as_declared": catalog.accepted_count,
        "quarantined": catalog.quarantined_count,
        "screening_complete": result.screening_complete,
        "passes_stc_and_cold_voc_screening": result.passes_screening,
        "missing": result.missing,
        "stc_issues": result.stc.issues if result.stc else [],
        "temperature_issues": result.temperature.issues if result.temperature else [],
        "temperature_warnings": result.temperature.warnings if result.temperature else [],
        "real_physics_ready": result.physics.real_physics_ready,
        "model_missing": result.physics.missing,
        "model_unverified": result.physics.unverified,
        "note": "Research metadata only; not an OEM model calibration or installation approval",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


from __future__ import annotations

import csv

from dataclasses import dataclass
from math import isfinite
from pathlib import Path


# ============================================================
# PARAMETER DATA MODELS
# ============================================================

@dataclass(frozen=True)
class ParameterRecord:
    value: str | None
    source_id: str
    evidence: str
    page: str


@dataclass(frozen=True)
class Component:
    component_id: str
    component_type: str
    parameters: dict[str, ParameterRecord]

    def number(
        self,
        name: str,
        required: bool = True,
    ) -> float | None:

        record = self.parameters.get(name)

        if record is None or record.value is None:
            if required:
                raise ValueError(
                    f"{self.component_id}: "
                    f"missing parameter {name}"
                )

            return None

        try:
            value = float(record.value)

        except ValueError as exc:
            raise ValueError(
                f"{self.component_id}: "
                f"invalid numeric parameter {name}"
            ) from exc

        if not isfinite(value):
            raise ValueError(
                f"{self.component_id}: "
                f"non-finite parameter {name}"
            )

        return value


# ============================================================
# STC CHECK RESULTS
# ============================================================

@dataclass(frozen=True)
class STCCheck:
    string_vmp_v: float
    string_voc_v: float

    mppt_imp_a: float
    mppt_isc_a: float

    issues: tuple[str, ...]

    @property
    def passes_stc_checks(self) -> bool:
        return len(self.issues) == 0


# ============================================================
# LOAD REAL COMPONENT PARAMETERS
# ============================================================

def load_component_catalog(
    filename: str | Path,
) -> dict[str, Component]:

    required_columns = {
        "component_id",
        "component_type",
        "parameter",
        "value",
        "source_id",
        "page",
        "evidence",
    }

    grouped = {}

    with Path(filename).open(
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        if not required_columns.issubset(
            set(reader.fieldnames or ())
        ):
            raise ValueError(
                "Component CSV has missing columns"
            )

        for row in reader:

            component_id = row["component_id"]
            component_type = row["component_type"]
            name = row["parameter"]

            if (
                not component_id
                or not name
                or component_type not in {
                    "panel",
                    "inverter",
                }
                or not row["source_id"]
                or not row["evidence"]
            ):
                raise ValueError(
                    "Invalid component record"
                )

            if component_id not in grouped:

                grouped[component_id] = {
                    "type": component_type,
                    "parameters": {},
                }

            entry = grouped[component_id]

            if entry["type"] != component_type:
                raise ValueError(
                    "Conflicting component types"
                )

            if name in entry["parameters"]:
                raise ValueError(
                    f"Duplicate parameter: "
                    f"{component_id}/{name}"
                )

            raw = row["value"]

            entry["parameters"][name] = ParameterRecord(
                value=(
                    raw
                    if raw and raw.strip()
                    else None
                ),
                source_id=row["source_id"],
                evidence=row["evidence"],
                page=row["page"] or "",
            )

    return {
        component_id: Component(
            component_id=component_id,
            component_type=data["type"],
            parameters=data["parameters"],
        )

        for component_id, data in grouped.items()
    }


# ============================================================
# MPPT ELECTRICAL CHECK AT STC
# ============================================================

def check_mppt_at_stc(
    panel: Component,
    inverter: Component,
    modules_per_string: int,
    strings_per_mppt: int,
) -> STCCheck:

    """
    Preliminary STC electrical screening.

    This calculation does not approve
    a physical installation.
    """

    if panel.component_type != "panel":
        raise ValueError(
            "Expected a panel"
        )

    if inverter.component_type != "inverter":
        raise ValueError(
            "Expected an inverter"
        )

    if (
        type(modules_per_string) is not int
        or type(strings_per_mppt) is not int
        or modules_per_string <= 0
        or strings_per_mppt <= 0
    ):
        raise ValueError(
            "String counts must be positive integers"
        )

    # Series connection increases voltage.
    vmp = (
        modules_per_string
        * panel.number("v_mp_v")
    )

    voc = (
        modules_per_string
        * panel.number("v_oc_v")
    )

    # Parallel strings increase current.
    imp = (
        strings_per_mppt
        * panel.number("i_mp_a")
    )

    isc = (
        strings_per_mppt
        * panel.number("i_sc_a")
    )

    issues = []

    if strings_per_mppt > inverter.number(
        "strings_per_mppt"
    ):
        issues.append(
            "TOO_MANY_STRINGS"
        )

    if not (
        inverter.number("mppt_min_v")
        <= vmp
        <= inverter.number("mppt_max_v")
    ):
        issues.append(
            "MPPT_VOLTAGE_OUTSIDE_WINDOW"
        )

    if voc > inverter.number("max_dc_v"):
        issues.append(
            "INVERTER_DC_OVERVOLTAGE_AT_STC"
        )

    if voc > panel.number("max_system_v"):
        issues.append(
            "PANEL_SYSTEM_VOLTAGE_EXCEEDED_AT_STC"
        )

    if imp > inverter.number(
        "max_operating_current_per_mppt_a"
    ):
        issues.append(
            "MPPT_OPERATING_CURRENT_EXCEEDED"
        )

    if isc > inverter.number(
        "max_short_circuit_current_per_mppt_a"
    ):
        issues.append(
            "MPPT_SHORT_CIRCUIT_LIMIT_EXCEEDED"
        )

    return STCCheck(
        string_vmp_v=vmp,
        string_voc_v=voc,
        mppt_imp_a=imp,
        mppt_isc_a=isc,
        issues=tuple(issues),
    )


# ============================================================
# TEMPERATURE-DEPENDENT VOLTAGE SCREENING
# ============================================================

@dataclass(frozen=True)
class TemperatureVoltageCheck:
    cold_string_voc_v: float
    hot_string_voc_v: float

    inverter_max_dc_v: float
    panel_max_system_v: float

    issues: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def within_dc_voltage_limits(self) -> bool:
        return len(self.issues) == 0


def check_string_temperature_voltage(
    panel: Component,
    inverter: Component,
    modules_per_string: int,
    min_cell_temperature_c: float,
    max_cell_temperature_c: float,
) -> TemperatureVoltageCheck:

    """
    Estimate string open-circuit voltage at
    selected PV cell temperatures.

    Uses linear datasheet Voc temperature
    coefficient.

    This is a preliminary screening only,
    not an installation approval.
    """

    # 1. Validate component types.

    if panel.component_type != "panel":
        raise ValueError(
            "Expected a panel"
        )

    if inverter.component_type != "inverter":
        raise ValueError(
            "Expected an inverter"
        )

    if (
        type(modules_per_string) is not int
        or modules_per_string <= 0
    ):
        raise ValueError(
            "modules_per_string must be "
            "a positive integer"
        )

    # 2. Validate temperatures.

    temperatures = (
        min_cell_temperature_c,
        max_cell_temperature_c,
    )

    for temperature in temperatures:

        if (
            not isinstance(
                temperature,
                (int, float),
            )
            or isinstance(temperature, bool)
            or not isfinite(temperature)
            or temperature < -273.15
        ):
            raise ValueError(
                "Invalid cell temperature"
            )

    if min_cell_temperature_c > max_cell_temperature_c:
        raise ValueError(
            "Minimum temperature exceeds maximum"
        )

    # 3. Read datasheet parameters.

    voc_stc = panel.number("v_oc_v")

    beta_voc = panel.number(
        "beta_voc_per_C"
    )

    inverter_max = inverter.number(
        "max_dc_v"
    )

    panel_max = panel.number(
        "max_system_v"
    )

    if (
        voc_stc <= 0
        or inverter_max <= 0
        or panel_max <= 0
    ):
        raise ValueError(
            "Voltage limits must be positive"
        )

    if not -0.02 < beta_voc < 0:
        raise ValueError(
            "Invalid relative Voc "
            "temperature coefficient"
        )

    # 4. Calculate string Voc.

    def string_voc(
        temperature_c: float,
    ) -> float:

        module_voc = voc_stc * (
            1.0
            + beta_voc * (temperature_c - 25.0)
        )

        if module_voc <= 0:
            raise ValueError(
                "Temperature model returned invalid Voc"
            )

        return (
            modules_per_string
            * module_voc
        )

    cold_voc = string_voc(
        min_cell_temperature_c
    )

    hot_voc = string_voc(
        max_cell_temperature_c
    )

    # 5. Check absolute DC limits.

    issues = []

    if cold_voc > inverter_max:
        issues.append(
            "INVERTER_MAX_DC_VOLTAGE_EXCEEDED"
        )

    if cold_voc > panel_max:
        issues.append(
            "PANEL_MAX_SYSTEM_VOLTAGE_EXCEEDED"
        )

    # 6. Conditions requiring OEM review.

    warnings = [
        "MPPT_TEMPERATURE_WINDOW_NOT_VERIFIED",
    ]

    if (
        inverter.component_id
        == "SUNGROW_SG110CX_V152"
        and cold_voc > 1000.0
    ):
        warnings.append(
            "OEM_CONNECTOR_REVIEW_ABOVE_1000V"
        )

    return TemperatureVoltageCheck(
        cold_string_voc_v=cold_voc,
        hot_string_voc_v=hot_voc,

        inverter_max_dc_v=inverter_max,
        panel_max_system_v=panel_max,

        issues=tuple(issues),
        warnings=tuple(warnings),
    )

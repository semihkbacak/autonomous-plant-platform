
"""Standalone OEM screening demo. No equipment access."""

from dataclasses import asdict
import json
from pathlib import Path

from simulator.solar.component_catalog import (
    load_component_catalog,
)
from simulator.solar.oem_design_review import (
    MPPTAssignment,
    review_oem_design,
)


CATALOG_FILE = (
    Path(__file__).resolve().parent
    / "data/solar/reference/ges_component_parameters.csv"
)


def main():
    catalog = load_component_catalog(CATALOG_FILE)

    scenarios = (
        (
            "SMA / Trina / single string",
            review_oem_design(
                catalog,
                inverter_id="SMA_STP50_40",
                assignments=(
                    MPPTAssignment(
                        1, "TRINA_TSM445_NEG9R28", 15, 1
                    ),
                ),
                min_cell_temperature_c=-10,
                max_cell_temperature_c=70,
                ambient_temperature_c=25,
                requested_active_kw=30,
                requested_reactive_kvar=10,
            ),
        ),
        (
            "Sungrow / Jinko / two strings / 50 C",
            review_oem_design(
                catalog,
                inverter_id="SUNGROW_SG110CX_V152",
                assignments=(
                    MPPTAssignment(
                        1, "JINKO_JKM585N72HL4V", 18, 2
                    ),
                ),
                min_cell_temperature_c=-10,
                max_cell_temperature_c=70,
                ambient_temperature_c=50,
                requested_active_kw=90,
                requested_reactive_kvar=60,
            ),
        ),
    )

    for label, result in scenarios:
        print("\n===", label, "===")

        print(
            json.dumps(
                asdict(result),
                ensure_ascii=False,
                indent=2,
            )
        )

        print(
            "PRELIMINARY PASS:",
            result.passes_preliminary_checks,
        )

        print(
            "INSTALLATION APPROVED:",
            result.approved_for_installation,
        )


if __name__ == "__main__":
    main()

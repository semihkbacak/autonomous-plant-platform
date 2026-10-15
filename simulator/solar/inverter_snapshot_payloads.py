
from __future__ import annotations

import json

from dataclasses import asdict, is_dataclass


SOURCE_ID = "APP_SYNTHETIC_GES_DEMO"
SOURCE_URL = "project://demo_ges_timeseries.py"
MODEL_ID = "APP_SYNTHETIC_GES_DEMO_V1"


def build_demo_inverter_snapshot_payloads(
    pipeline,
) -> dict[str, dict]:
    """
    Capture the configuration actually used by
    the APP synthetic GES demo.

    Includes inverter, PV array, module, surface,
    and site settings.

    Values are NOT manufacturer-verified hardware
    parameters.
    """

    if not pipeline.assets:
        raise ValueError("No solar assets")

    snapshots = {}

    for asset in pipeline.assets:
        inverter_id = asset.inverter.inverter_id

        if inverter_id in snapshots:
            raise ValueError("Duplicate inverter ID")

        values = {}

        components = (
            ("inverter", asset.inverter),
            ("array", asset.array),
            ("surface", asset.surface),
            ("site", pipeline.site),
        )

        for prefix, component in components:
            if not is_dataclass(component):
                raise ValueError(
                    f"{prefix} is not a dataclass"
                )

            for name, value in asdict(
                component
            ).items():

                # Already stored as component_id.
                if (
                    prefix == "inverter"
                    and name == "inverter_id"
                ):
                    continue

                values[f"{prefix}.{name}"] = {
                    "value": value,
                    "source_id": SOURCE_ID,
                    "source_url": SOURCE_URL,
                    "evidence": (
                        "Synthetic APP demo configuration; "
                        "not an OEM datasheet"
                    ),
                }

        payload = {
            "component_id": inverter_id,
            "model_id": MODEL_ID,
            "values": values,
        }

        # Reject parameters that cannot be
        # stored reliably as JSON.
        try:
            json.dumps(
                payload,
                allow_nan=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid configuration for {inverter_id}"
            ) from exc

        snapshots[inverter_id] = payload

    return snapshots

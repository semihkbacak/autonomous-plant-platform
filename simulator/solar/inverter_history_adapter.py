
from __future__ import annotations

import sqlite3

from typing import Mapping

from simulator.solar.inverter_history_writer import (
    InverterHistoryRow,
    PlantTotals,
    save_inverter_interval,
)


def build_inverter_history_rows(
    record,
    run_id: int,
    *,
    expected_inverter_ids: tuple[str, ...],
    parameter_snapshot_ids: Mapping[str, str],
) -> list[InverterHistoryRow]:
    """
    Convert real APP inverter results into
    Step 11 Historian records.

    Plant-wide alarms are not duplicated as
    inverter-specific alarms.

    No database changes occur here.
    """

    # 1. Validate run and inverter identities.

    if type(run_id) is not int or run_id <= 0:
        raise ValueError("Invalid run_id")

    if (
        not expected_inverter_ids
        or len(set(expected_inverter_ids))
        != len(expected_inverter_ids)
        or any(
            not isinstance(item, str)
            or not item.strip()
            for item in expected_inverter_ids
        )
    ):
        raise ValueError(
            "Invalid expected inverter IDs"
        )

    expected = set(expected_inverter_ids)

    results = tuple(record.inverter_results)

    actual_ids = [
        inverter.inverter_id
        for inverter in results
    ]

    if (
        len(actual_ids) != len(set(actual_ids))
        or set(actual_ids) != expected
    ):
        raise ValueError(
            "Missing, extra or duplicate inverter result"
        )

    if set(parameter_snapshot_ids) != expected:
        raise ValueError(
            "Missing or extra parameter snapshot"
        )

    # 2. Separate plant-wide and inverter alarms.

    inverter_alarms = {
        inverter_id: []
        for inverter_id in expected_inverter_ids
    }

    for label in record.active_alarms:

        if not isinstance(label, str):
            raise ValueError(
                "Invalid alarm label"
            )

        if ":" not in label:
            # Unscoped plant alarm.
            # Existing alarm_events handles it.
            continue

        code, target_id = label.split(":", 1)

        if not code or target_id not in expected:
            raise ValueError(
                f"Unknown inverter alarm target: {label}"
            )

        if code not in inverter_alarms[target_id]:
            inverter_alarms[target_id].append(code)

    # 3. Preserve record provenance.

    quality_flags = tuple(
        dict.fromkeys(
            (*record.quality_flags, "estimated")
        )
    )

    source_types = tuple(record.source_types)

    if not source_types:
        raise ValueError(
            "Missing simulation source types"
        )

    # Snapshot power is assumed constant
    # across the 15-minute interval.
    power_time_semantics = (
        "snapshot_constant_assumption"
    )

    # 4. Convert each inverter.

    rows = []

    for inverter in results:

        inverter_id = inverter.inverter_id

        snapshot_id = parameter_snapshot_ids[
            inverter_id
        ]

        if (
            not isinstance(snapshot_id, str)
            or not snapshot_id.strip()
        ):
            raise ValueError(
                "Empty parameter snapshot ID"
            )

        status = (
            inverter.status.value
            if hasattr(inverter.status, "value")
            else inverter.status
        )

        row = InverterHistoryRow(
            run_id=run_id,
            inverter_id=inverter_id,

            start_utc=record.start_utc,
            end_utc=record.end_utc,

            # The current InverterResult does not
            # carry an actual DC voltage sample.
            dc_voltage_v=None,

            dc_offered_kw=inverter.dc_offered_kw,
            dc_accepted_kw=inverter.dc_accepted_kw,
            dc_rejected_kw=inverter.dc_rejected_kw,

            ac_unclipped_kw=inverter.ac_unclipped_kw,
            ac_available_kw=inverter.ac_available_kw,
            ac_dispatched_kw=inverter.ac_dispatched_kw,

            conversion_loss_kw=(
                inverter.conversion_loss_kw
            ),
            clipping_loss_kw=(
                inverter.clipping_loss_kw
            ),
            curtailment_kw=inverter.curtailment_kw,

            interval_energy_kwh=(
                inverter.ac_dispatched_kw * 0.25
            ),

            status=status,

            active_alarms=tuple(
                inverter_alarms[inverter_id]
            ),

            reasons=tuple(inverter.reasons),

            quality_flags=quality_flags,
            source_types=source_types,

            parameter_snapshot_id=snapshot_id,
            power_time_semantics=power_time_semantics,

            # No original sensor or reception
            # timestamps exist in this result.
            source_timestamp_utc=None,
            received_at_utc=None,
        )

        rows.append(row)

    return rows


def append_simulated_inverter_interval(
    db: sqlite3.Connection,
    *,
    run_id: int,
    record,
    expected_inverter_ids: tuple[str, ...],
    parameter_snapshot_ids: Mapping[str, str],
) -> None:
    """
    Append real APP simulation results
    inside the caller's existing transaction.

    The parent production_intervals row
    must already exist.

    Does not commit.
    """

    rows = build_inverter_history_rows(
        record,
        run_id,
        expected_inverter_ids=expected_inverter_ids,
        parameter_snapshot_ids=parameter_snapshot_ids,
    )

    plant = PlantTotals(
        run_id=run_id,
        start_utc=record.start_utc,
        end_utc=record.end_utc,
        available_power_kw=record.available_power_kw,
        dispatched_power_kw=record.dispatched_power_kw,
        interval_energy_kwh=record.interval_energy_kwh,
    )

    save_inverter_interval(
        db,
        rows,
        plant,
        expected_inverter_ids=expected_inverter_ids,
    )

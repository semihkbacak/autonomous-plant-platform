
"""GES v0.4 - Farkli MPPT kosullariyla 1 gunluk simulasyon.

Her inverterde iki bagimsiz MPPT kanali bulunur.
MPPT kanallarinin panel egimi, azimutu veya
seri panel sayisi birbirinden farklidir.

Tamamen sentetik simulasyondur.
Gercek santral veya OT kontrolu icermez.
"""

from __future__ import annotations

import sqlite3

from dataclasses import replace
from pathlib import Path
from math import isclose

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.pq_dispatch import (
    PQCapability,
)

from simulator.solar.solar_stress import (
    make_stress_intervals,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)


OUTPUT = Path("outputs/ges_v04_diverse_mppt")


def build_diverse_pipeline():

    base = build_integrated_demo_pipeline()

    configs = {}

    for inverter_id, entry in base.mppt_configs.items():

        channels = list(entry.channels)

        if inverter_id == "INV_1":

            # MPPT 1: Guneydogu, 20 derece
            channels[0] = replace(
                channels[0],
                surface=replace(
                    channels[0].surface,
                    tilt_deg=20.0,
                    azimuth_deg=135.0,
                ),
            )

            # MPPT 2: Guney, 30 derece
            channels[1] = replace(
                channels[1],
                surface=replace(
                    channels[1].surface,
                    tilt_deg=30.0,
                    azimuth_deg=180.0,
                ),
            )

        elif inverter_id == "INV_2":

            # MPPT 1: Guneybati, 35 derece
            channels[0] = replace(
                channels[0],
                surface=replace(
                    channels[0].surface,
                    tilt_deg=35.0,
                    azimuth_deg=225.0,
                ),
            )

            # MPPT 2: Bati-guneybati, 50 derece.
            # Bu kanalda seri panel sayisi da farkli.
            channels[1] = replace(
                channels[1],
                surface=replace(
                    channels[1].surface,
                    tilt_deg=50.0,
                    azimuth_deg=250.0,
                ),
                array=replace(
                    channels[1].array,
                    modules_per_string=9,
                ),
            )

        configs[inverter_id] = replace(
            entry,
            channels=tuple(channels),
        )

    return IntegratedSolarPhysicsPipeline(
        site=base.site,
        assets=base.assets,
        mppt_configs=configs,
    )


def main():

    pipeline = build_diverse_pipeline()

    simulator = SolarTimeSeriesSimulator(pipeline)

    # Sentetik P-Q parametreleri.
    capabilities = {
        iid: PQCapability(
            nameplate_kva=10.0,
            rated_active_kw=10.0,
        )
        for iid in pipeline.inverter_ids
    }

    reactive_requests = {
        iid: 8.0
        for iid in pipeline.inverter_ids
    }

    print("=== GES FARKLI MPPT SENARYOSU ===")
    print("2 inverter / 4 MPPT / 1 gun")
    print("SIMULATION ONLY - NO OT CONTROL")

    for interval in make_stress_intervals(1):

        simulator.step(
            replace(
                interval,
                pq_capabilities=capabilities,
                reactive_requests_kvar=reactive_requests,
            )
        )

    assert len(simulator.records) == 96

    # Gunesli bir anda kanallar arasindaki
    # DC uretim farklarini karsilastir.
    peak_record = max(
        simulator.records,
        key=lambda record: sum(
            report.dc.dc_accepted_kw
            for report in record.mppt_reports
        ),
    )

    print()
    print("=== TEPE DC URETIM ANI ===")
    print(peak_record.start_utc.isoformat())

    values = []

    for report in peak_record.mppt_reports:

        for channel in report.dc.channels:

            values.append(channel.accepted_kw)

            print(
                report.inverter_id,
                f"MPPT {channel.channel}",
                f"Vmp={channel.voltage_v:.2f} V",
                f"DC={channel.accepted_kw:.4f} kW",
            )

    assert len(values) == 4

    assert any(value > 0 for value in values)

    # Tum kanallarin birebir ayni uretimi
    # vermedigini kontrol et.
    different = any(
        not isclose(
            value,
            values[0],
            rel_tol=1e-3,
            abs_tol=1e-4,
        )
        for value in values[1:]
    )

    if not different:
        raise AssertionError(
            "MPPT kanallari farkli uretim gostermiyor"
        )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_path = OUTPUT / "historian.sqlite3"

    historian = SolarHistorian(db_path)

    run_id = historian.save_simulation(
        simulator,
        scenario="GES_V04_DIVERSE_MPPT_SYNTHETIC",
        inverter_snapshot_payloads=(
            build_integrated_snapshots(pipeline)
        ),
    )

    with sqlite3.connect(db_path) as db:

        db.execute("PRAGMA foreign_keys = ON")

        mppt_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_mppt_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        pq_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_pq_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        inverter_count = db.execute(
            """
            SELECT COUNT(*)
            FROM ges_inverter_intervals
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()[0]

        fk_errors = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert mppt_count == 384
    assert pq_count == 192
    assert inverter_count == 192
    assert not fk_errors

    energy = simulator.records[-1].cumulative_energy_kwh

    print()
    print("=== SONUCLAR ===")
    print("Run ID:", run_id)
    print("Tesis araliklari:", len(simulator.records))
    print("Inverter kayitlari:", inverter_count)
    print("MPPT kayitlari:", mppt_count)
    print("P-Q kayitlari:", pq_count)
    print("Toplam AC enerji:", round(energy, 4), "kWh")
    print("Foreign key errors:", fk_errors)
    print("Veritabani:", db_path)

    print()
    print("GES DIVERSE MPPT SIMULATION OK")


if __name__ == "__main__":
    main()

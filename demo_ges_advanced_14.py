
from pathlib import Path

from demo_ges_timeseries import build_demo_pipeline

from simulator.solar.component_catalog import (
    load_component_catalog,
)

from simulator.solar.multi_mppt_physics import (
    MPPTArray,
    MPPTLimits,
    calculate_multi_mppt_dc,
)

from simulator.solar.oem_model_readiness import (
    assess_oem_readiness,
)

from simulator.solar.pq_dispatch import (
    PQCapability,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


ROOT = Path(__file__).resolve().parent


def main():
    pipeline = build_demo_pipeline()

    weather = load_weather_intervals_csv(
        ROOT / "data/solar/demo_weather_15m.csv"
    )[1].weather

    print("\n=== 14C: MULTI-MPPT DC ===")

    dc = calculate_multi_mppt_dc(
        site=pipeline.site,
        weather=weather,

        arrays=(
            MPPTArray(
                1,
                pipeline.assets[0].array,
                pipeline.assets[0].surface,
            ),

            MPPTArray(
                2,
                pipeline.assets[1].array,
                pipeline.assets[1].surface,
            ),
        ),

        limits=MPPTLimits(
            mppt_count=2,
            min_v=200,
            max_v=800,
            max_dc_v=1000,
            max_operating_a=30,
            max_short_circuit_a=40,
            max_strings=2,
        ),
    )

    for channel in dc.channels:
        print(
            f"MPPT {channel.channel}: "
            f"Vmp={channel.voltage_v:.2f} V, "
            f"DC={channel.accepted_kw:.3f} kW"
        )

    print(
        "Accepted DC total:",
        round(dc.dc_accepted_kw, 3),
        "kW",
    )

    print("\n=== 14D: OEM READINESS ===")

    catalog = load_component_catalog(
        ROOT
        / "data/solar/reference/ges_component_parameters.csv"
    )

    readiness = assess_oem_readiness(
        catalog["TRINA_TSM445_NEG9R28"],
        catalog["SMA_STP50_40"],
    )

    print(
        "OEM model ready:",
        readiness.real_physics_ready,
    )

    print(
        "Missing:",
        readiness.missing,
    )

    print("\n=== 14E: P-Q DISPATCH ===")

    baseline = pipeline.simulate(
        weather
    )

    constrained = pipeline.simulate(
        weather,
        pq_capabilities={
            "INV_1": PQCapability(5, 10),
            "INV_2": PQCapability(5, 10),
        },

        reactive_requests_kvar={
            "INV_1": 4,
            "INV_2": 4,
        },
    )

    print(
        "Baseline active power:",
        round(
            baseline.plant.dispatched_power_kw,
            3,
        ),
        "kW",
    )

    print(
        "PQ-constrained active power:",
        round(
            constrained.plant.dispatched_power_kw,
            3,
        ),
        "kW",
    )

    print(
        "Curtailment:",
        round(
            constrained.plant.curtailed_power_kw,
            3,
        ),
        "kW",
    )

    print("\nSIMULATION ONLY - NO OT CONTROL")


if __name__ == "__main__":
    main()

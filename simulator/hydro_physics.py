RHO_WATER_KG_M3 = 1000.0
GRAVITY_M_S2 = 9.81

def calculate_hydro_power_mw(
    flow_m3_s: float,
    net_head_m: float,
    turbine_efficiency: float,
    generator_efficiency: float,
) -> float:

    total_efficiency = (
        turbine_efficiency * generator_efficiency
    )

    power_w = (
        RHO_WATER_KG_M3
        * GRAVITY_M_S2
        * flow_m3_s
        * net_head_m
        * total_efficiency
    )

    return power_w / 1_000_000.0

def calculate_hydro_power_mw(
    flow_m3_s: float,
    net_head_m: float,
    turbine_efficiency: float,
    generator_efficiency: float,
) -> float:

    total_efficiency = (
        turbine_efficiency * generator_efficiency
    )

    power_w = (
        RHO_WATER_KG_M3
        * GRAVITY_M_S2
        * flow_m3_s
        * net_head_m
        * total_efficiency
    )

    return power_w / 1_000_000.0


def calculate_required_flow_m3_s(
        target_power_mw: float,
        net_head_m: float,
        turbine_efficiency: float,
        generator_efficiency: float,
    ) -> float:

        total_efficiency = (
            turbine_efficiency * generator_efficiency
        )

        target_power_w = target_power_mw * 1_000_000.0

        flow_m3_s = target_power_w / (
            RHO_WATER_KG_M3
            * GRAVITY_M_S2
            * net_head_m
            * total_efficiency
        )

        return flow_m3_s

def calculate_net_head_m(
    gross_head_m: float,
    hydraulic_loss_m: float,
) -> float:

    return max(
        0.0,
        gross_head_m - hydraulic_loss_m,
    )
from math import pi, sqrt
def calculate_jet_velocity_m_s(
    net_head_m: float,
) -> float:

    return sqrt(
        2.0
        * GRAVITY_M_S2
        * net_head_m
    )
def calculate_pelton_flow_m3_s(
    net_head_m: float,
    needle_opening_pct: float,
    nozzle_diameter_m: float,
    discharge_coefficient: float,
    jet_count: int,
) -> float:

    opening_fraction = max(
        0.0,
        min(needle_opening_pct / 100.0, 1.0),
    )

    nozzle_area_m2 = (
        pi
        * nozzle_diameter_m**2
        / 4.0
    )

    jet_velocity_m_s = calculate_jet_velocity_m_s(
        net_head_m
    )

    flow_per_jet_m3_s = (
        discharge_coefficient
        * nozzle_area_m2
        * jet_velocity_m_s
        * opening_fraction
    )

    return flow_per_jet_m3_s * jet_count

def calculate_required_needle_opening_pct(
    target_power_mw: float,
    net_head_m: float,
    nozzle_diameter_m: float,
    discharge_coefficient: float,
    jet_count: int,
    turbine_efficiency: float,
    generator_efficiency: float,
) -> float:

    full_open_flow_m3_s = calculate_pelton_flow_m3_s(
        net_head_m=net_head_m,
        needle_opening_pct=100.0,
        nozzle_diameter_m=nozzle_diameter_m,
        discharge_coefficient=discharge_coefficient,
        jet_count=jet_count,
    )

    full_open_power_mw = calculate_hydro_power_mw(
        flow_m3_s=full_open_flow_m3_s,
        net_head_m=net_head_m,
        turbine_efficiency=turbine_efficiency,
        generator_efficiency=generator_efficiency,
    )

    if full_open_power_mw <= 0.0:
        return 0.0

    opening_pct = (
        target_power_mw
        / full_open_power_mw
        * 100.0
    )

    return max(
        0.0,
        min(opening_pct, 100.0),
    )
def move_toward_target(
    current_value: float,
    target_value: float,
    max_step: float,
) -> float:

    if target_value > current_value:
        return min(
            current_value + max_step,
            target_value,
        )

    if target_value < current_value:
        return max(
            current_value - max_step,
            target_value,
        )

    return current_value
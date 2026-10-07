import pytest

from simulator.hydro_physics import (
    calculate_hydro_power_mw,
    calculate_required_flow_m3_s,
    calculate_net_head_m,
    calculate_jet_velocity_m_s,
    calculate_pelton_flow_m3_s,
    calculate_required_needle_opening_pct,
    move_toward_target,

)
def test_required_flow_reproduces_target_power():
    target_power_mw = 10.0

    required_flow = calculate_required_flow_m3_s(
        target_power_mw=target_power_mw,
        net_head_m=300.0,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    calculated_power = calculate_hydro_power_mw(
        flow_m3_s=required_flow,
        net_head_m=300.0,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    assert calculated_power == pytest.approx(
        target_power_mw,
        rel=0.001,
    )

def test_calculate_hydro_power_mw():
    result = calculate_hydro_power_mw(
        flow_m3_s=2.5,
        net_head_m=300.0,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    assert result == pytest.approx(6.423, rel=0.001)

def test_net_head_is_gross_head_minus_losses():
    result = calculate_net_head_m(
        gross_head_m=310.0,
        hydraulic_loss_m=10.0,
    )

    assert result == 300.0

def test_net_head_cannot_be_negative():
    result = calculate_net_head_m(
        gross_head_m=10.0,
        hydraulic_loss_m=20.0,
    )

    assert result == 0.0

def test_pelton_jet_velocity_is_positive():
    velocity = calculate_jet_velocity_m_s(
        net_head_m=300.0,
    )

    assert velocity > 0.0
    assert velocity == pytest.approx(
        76.72,
        rel=0.01,
    )
def test_closed_pelton_needle_produces_zero_flow():
    flow = calculate_pelton_flow_m3_s(
        net_head_m=300.0,
        needle_opening_pct=0.0,
        nozzle_diameter_m=0.08,
        discharge_coefficient=0.98,
        jet_count=1,
    )

    assert flow == 0.0
def test_demo_pelton_full_open_capacity_matches_unit_scale():
    flow = calculate_pelton_flow_m3_s(
        net_head_m=300.0,
        needle_opening_pct=100.0,
        nozzle_diameter_m=0.16,
        discharge_coefficient=0.98,
        jet_count=4,
    )

    power = calculate_hydro_power_mw(
        flow_m3_s=flow,
        net_head_m=300.0,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    assert power == pytest.approx(
        15.54,
        rel=0.02,
    )
def test_governor_calculates_needle_opening_for_target_power():
    opening_pct = calculate_required_needle_opening_pct(
        target_power_mw=10.0,
        net_head_m=300.0,
        nozzle_diameter_m=0.16,
        discharge_coefficient=0.98,
        jet_count=4,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    assert opening_pct > 0.0
    assert opening_pct < 100.0
def test_governor_limits_needle_opening_to_100_percent():
    opening_pct = calculate_required_needle_opening_pct(
        target_power_mw=30.0,
        net_head_m=300.0,
        nozzle_diameter_m=0.16,
        discharge_coefficient=0.98,
        jet_count=4,
        turbine_efficiency=0.90,
        generator_efficiency=0.97,
    )

    assert opening_pct == 100.0
def test_move_toward_target_increases_by_max_step():
    result = move_toward_target(
        current_value=20.0,
        target_value=70.0,
        max_step=5.0,
    )

    assert result == 25.0


def test_move_toward_target_decreases_by_max_step():
    result = move_toward_target(
        current_value=70.0,
        target_value=30.0,
        max_step=5.0,
    )

    assert result == 65.0


def test_move_toward_target_does_not_overshoot():
    result = move_toward_target(
        current_value=68.0,
        target_value=70.0,
        max_step=5.0,
    )

    assert result == 70.0
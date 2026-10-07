from core.models import PlantState, UnitState, UnitStatus
from core.scheduler import (
    total_active_power_mw,
    power_deficit_mw,
    select_start_candidate,
    recommend_start_for_target,
)
def test_total_active_power_is_sum_of_units():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                active_power_mw=10.0,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                active_power_mw=5.0,
            ),
        ]
    )

    result = total_active_power_mw(plant)

    assert result == 15.0
def test_power_deficit_is_target_minus_current_power():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                active_power_mw=10.0,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                active_power_mw=5.0,
            )
        ]
    )

    result = power_deficit_mw(
        plant,
        target_power_mw=25.0,
    )

    assert result == 10.0
def test_select_start_candidate_returns_stopped_unit():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                status=UnitStatus.RUNNING,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                status=UnitStatus.STOPPED,
            ),
        ]
    )

    result = select_start_candidate(plant)

    assert result == "UNIT_2"

def test_recommend_start_when_power_is_below_target():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                active_power_mw=10.0,
                status=UnitStatus.RUNNING,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                active_power_mw=0.0,
                status=UnitStatus.STOPPED,
            ),
        ]
    )

    result = recommend_start_for_target(
        plant,
        target_power_mw=20.0,
    )

    assert result == "UNIT_2"
def test_recommend_no_start_when_target_is_already_met():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                active_power_mw=12.0,
                status=UnitStatus.RUNNING,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                active_power_mw=0.0,
                status=UnitStatus.STOPPED,
            ),
        ]
    )

    result = recommend_start_for_target(
        plant,
        target_power_mw=10.0,
    )

    assert result is None  

def test_recommend_no_start_when_target_is_already_met():
    plant = PlantState(
        units=[
            UnitState(
                unit_id="UNIT_1",
                rated_power_mw=15.0,
                active_power_mw=12.0,
                status=UnitStatus.RUNNING,
            ),
            UnitState(
                unit_id="UNIT_2",
                rated_power_mw=15.0,
                active_power_mw=0.0,
                status=UnitStatus.STOPPED,
            ),
        ]
    )

    result = recommend_start_for_target(
        plant,
        target_power_mw=10.0,
    )

    assert result is None 
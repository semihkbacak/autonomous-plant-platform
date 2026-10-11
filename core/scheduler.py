from core.models import PlantState, UnitStatus



def total_active_power_mw(
    plant: PlantState,
) -> float:
    return sum(
        unit.active_power_mw
        for unit in plant.units
    )


def power_deficit_mw(
    plant: PlantState,
    target_power_mw: float,
) -> float:
    current_power_mw = total_active_power_mw(
        plant
    )

    return (
        target_power_mw
        - current_power_mw
    )


def select_start_candidate(
    plant: PlantState,
) -> str | None:

    for unit in plant.units:
        if unit.status == UnitStatus.STOPPED:
            return unit.unit_id

    return None


def recommend_start_for_target(
    plant: PlantState,
    target_power_mw: float,
) -> str | None:

    deficit_mw = power_deficit_mw(
        plant,
        target_power_mw,
    )

    if deficit_mw <= 0:
        return None

    return select_start_candidate(
        plant
    )


# ============================================================
# PLANT DISPATCH
# ============================================================

def select_units_for_target(
    plant: PlantState,
    target_power_mw: float,
) -> list[str]:
    """
    Tesis toplam güç hedefini karşılamak için
    gerekli minimum sayıda üniteyi seçer.

    Örnek:

    UNIT_1 = 15 MW
    UNIT_2 = 15 MW

    hedef 8 MW:
        UNIT_1

    hedef 20 MW:
        UNIT_1 + UNIT_2
    """

    selected: list[str] = []

    accumulated_capacity_mw = 0.0

    for unit in plant.units:
        selected.append(
            unit.unit_id
        )

        accumulated_capacity_mw += (
            unit.rated_power_mw
        )

        if (
            accumulated_capacity_mw
            >= target_power_mw
        ):
            break

    return selected


def calculate_dispatch_setpoints(
    plant: PlantState,
    target_power_mw: float,
    selected_unit_ids: list[str],
) -> dict[str, float]:
    """
    Tesis güç hedefini seçilmiş ünitelere
    nominal güçleri oranında dağıtır.
    """

    selected_units = [
        unit
        for unit in plant.units
        if unit.unit_id
        in selected_unit_ids
    ]

    total_selected_capacity_mw = sum(
        unit.rated_power_mw
        for unit in selected_units
    )

    if total_selected_capacity_mw <= 0:
        return {}

    setpoints: dict[str, float] = {}

    for unit in selected_units:
        capacity_ratio = (
            unit.rated_power_mw
            / total_selected_capacity_mw
        )

        unit_target_mw = (
            target_power_mw
            * capacity_ratio
        )

        setpoints[unit.unit_id] = min(
            unit_target_mw,
            unit.rated_power_mw,
        )

    return setpoints
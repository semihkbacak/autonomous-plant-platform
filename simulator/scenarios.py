import random
from copy import deepcopy
from enum import Enum

from core.models import PlantState
class ScenarioType(str, Enum):
    NORMAL = "NORMAL"
    DEMAND_INCREASE = "DEMAND_INCREASE"
    UNIT_FAULT = "UNIT_FAULT"
    HIGH_TEMPERATURE = "HIGH_TEMPERATURE"
    HIGH_VIBRATION = "HIGH_VIBRATION"
    GRID_LOSS = "GRID_LOSS"
    LOW_HEADPOND = "LOW_HEADPOND"

def choose_random_scenario(seed: int | None = None) -> ScenarioType:
    rng = random.Random(seed)

    return rng.choice(list(ScenarioType))

def apply_plant_scenario(
    plant: PlantState,
    scenario: ScenarioType,
    seed: int | None = None,
) -> PlantState:

    updated_plant = deepcopy(plant)
    rng = random.Random(seed)

    if scenario == ScenarioType.NORMAL:
        return updated_plant

    if scenario == ScenarioType.GRID_LOSS:
        updated_plant.grid_available = False

    elif scenario == ScenarioType.LOW_HEADPOND:
        updated_plant.headpond_level_pct = 15.0

    elif scenario == ScenarioType.UNIT_FAULT:
        unit = rng.choice(updated_plant.units)
        unit.fault = True
        unit.ready = False

    elif scenario == ScenarioType.HIGH_TEMPERATURE:
        unit = rng.choice(updated_plant.units)
        unit.bearing_temperature_c = 85.0

    elif scenario == ScenarioType.HIGH_VIBRATION:
        unit = rng.choice(updated_plant.units)
        unit.vibration_mm_s = 9.0

    return updated_plant
# Üretim hedefini senaryoya göre değiştirir.
def apply_demand_scenario(
        target_power_mw: float,
        scenario: ScenarioType,
        seed: int | None = None,
    ) -> float:

        rng = random.Random(seed)

        if scenario == ScenarioType.DEMAND_INCREASE:
            increase_mw = rng.uniform(3.0, 10.0)

            return target_power_mw + increase_mw

        return target_power_mw
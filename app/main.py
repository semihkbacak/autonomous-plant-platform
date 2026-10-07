import asyncio
from contextlib import asynccontextmanager
from core.anomaly import detect_anomalies
from core.decision import build_decision_recommendations
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from ml.anomaly_model import (
    evaluate_plant_with_model,
)
from core.scheduler import total_active_power_mw
from core.models import (
    AlarmEvent,
    AlarmHistoryEntry,
    CommandResult,
    PlantState,
    RuntimeStatus,
    AnomalyFinding,
    DecisionRecommendation,
    MLAnomalyFinding,
    SystemAssessment,
)
from simulator.hydro import HydroPlantSimulator
from simulator.scenarios import ScenarioType


# ============================================================
# SIMULATOR
# ============================================================

sim = HydroPlantSimulator()


# ============================================================
# BACKGROUND SIMULATOR CLOCK
# ============================================================

async def simulator_clock() -> None:
    """
    Dijital ikizi otomatik olarak her saniye ilerletir.
    """

    while True:
        await asyncio.sleep(
            sim.AUTO_TICK_INTERVAL_S
        )

        if sim.auto_tick_enabled:
            sim.tick()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI açıldığında simulator clock başlatılır.

    Uygulama kapanırken görev güvenli şekilde durdurulur.
    """

    task = asyncio.create_task(
        simulator_clock()
    )

    try:
        yield

    finally:
        task.cancel()

        try:
            await task

        except asyncio.CancelledError:
            pass


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Autonomous Plant Platform - Simulator",
    version="0.2.0",
    description=(
        "Simulator-only MVP for a vendor-independent "
        "industrial autonomy platform. "
        "No real PLC/SCADA/OT system is connected. "
        "All process values are synthetic."
    ),
    lifespan=lifespan,
)


# ============================================================
# API REQUEST MODELS
# ============================================================

class ScenarioRequest(BaseModel):
    """
    Simülatöre uygulanacak sentetik test senaryosu.
    """

    scenario: ScenarioType

    seed: int | None = None


class PowerSetpointRequest(BaseModel):

    """
    Operatör veya scheduler tarafından gönderilen
    güç hedefi.
    """

    target_power_mw: float = Field(
        gt=0,
        allow_inf_nan=False,
    )
class PlantPowerTargetRequest(BaseModel):
    target_power_mw: float = Field(
        gt=0,
        allow_inf_nan=False,
    )

# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "simulator-only",
    }


# ============================================================
# PLANT STATE
# ============================================================

@app.get(
    "/api/v1/plant",
    response_model=PlantState,
)
def get_plant() -> PlantState:
    """
    HES dijital ikizinin mevcut durumunu döndürür.
    """

    return sim.snapshot()


# ============================================================
# ACTIVE ALARMS
# ============================================================

@app.get(
    "/api/v1/alarms/active",
    response_model=list[AlarmEvent],
)
def get_active_alarms() -> list[AlarmEvent]:
    """
    Şu anda aktif olan alarmları döndürür.
    """

    return sim.active_alarms()


# ============================================================
# ALARM HISTORY
# ============================================================

@app.get(
    "/api/v1/alarms/history",
    response_model=list[AlarmHistoryEntry],
)
def get_alarm_history() -> list[AlarmHistoryEntry]:
    """
    Daha önce oluşmuş alarm geçmişini döndürür.

    Alarm düzelmiş olsa bile geçmiş kaydı burada kalır.
    """

    return sim.alarm_history()


# ============================================================
# SIMULATOR RUNTIME
# ============================================================

@app.get(
    "/api/v1/sim/runtime",
    response_model=RuntimeStatus,
)
def runtime_status() -> RuntimeStatus:
    """
    Simülatör çalışma durumunu döndürür.
    """

    return sim.runtime_status()


# ============================================================
# AUTO TICK
# ============================================================

@app.post(
    "/api/v1/sim/auto",
    response_model=RuntimeStatus,
)
def set_auto_tick(
    active: bool,
) -> RuntimeStatus:
    """
    Otomatik tick özelliğini açar veya kapatır.
    """

    return sim.set_auto_tick(
        active
    )


# ============================================================
# UNIT START
# ============================================================

@app.post(
    "/api/v1/units/{unit_id}/start",
    response_model=CommandResult,
)
def start_unit(
    unit_id: str,
) -> CommandResult:
    """
    Bir ünite için START talebi gönderir.
    """

    result = sim.request_start(
        unit_id
    )

    if result.message == "Unknown unit":
        raise HTTPException(
            status_code=404,
            detail=result.message,
        )

    return result


# ============================================================
# UNIT POWER SETPOINT
# ============================================================

@app.post(
    "/api/v1/units/{unit_id}/power-setpoint",
    response_model=CommandResult,
)
def set_power_setpoint(
    unit_id: str,
    request: PowerSetpointRequest,
) -> CommandResult:
    """
    Bir ünite için MW güç hedefi gönderir.

    Talep simulator içindeki Safety Engine
    tarafından kontrol edilir.
    """

    result = sim.request_power_setpoint(
        unit_id=unit_id,
        target_power_mw=(
            request.target_power_mw
        ),
    )

    if result.message == "Unknown unit":
        raise HTTPException(
            status_code=404,
            detail=result.message,
        )

    return result


# ============================================================
# UNIT STOP
# ============================================================

@app.post(
    "/api/v1/units/{unit_id}/stop",
    response_model=CommandResult,
)
def stop_unit(
    unit_id: str,
) -> CommandResult:
    """
    Bir ünite için STOP talebi gönderir.
    """

    result = sim.request_stop(
        unit_id
    )

    if result.message == "Unknown unit":
        raise HTTPException(
            status_code=404,
            detail=result.message,
        )

    return result


# ============================================================
# MANUAL SIMULATOR TICK
# ============================================================

@app.post(
    "/api/v1/sim/tick",
    response_model=PlantState,
)
def tick() -> PlantState:
    """
    Dijital ikizi manuel olarak bir adım ilerletir.
    """

    return sim.tick()


# ============================================================
# SIMULATION SCENARIO
# ============================================================

@app.post(
    "/api/v1/sim/scenario",
    response_model=PlantState,
)
def apply_simulation_scenario(
    request: ScenarioRequest,
) -> PlantState:
    """
    HES dijital ikizine sentetik test senaryosu uygular.

    Örnek:
    GRID_LOSS
    HIGH_TEMPERATURE
    HIGH_VIBRATION
    UNIT_FAULT

    Gerçek PLC veya SCADA sistemiyle bağlantı kurulmaz.
    """

    return sim.apply_scenario(
        scenario=request.scenario,
        seed=request.seed,
    )


# ============================================================
# EMERGENCY STOP
# ============================================================

@app.post(
    "/api/v1/sim/emergency-stop",
    response_model=PlantState,
)
def emergency_stop(
    active: bool,
) -> PlantState:
    """
    Simülatör emergency-stop durumunu değiştirir.
    """

    return sim.set_emergency_stop(
        active
    )


# ============================================================
# MAINTENANCE LOCK
# ============================================================

@app.post(
    "/api/v1/sim/maintenance-lock",
    response_model=PlantState,
)
def maintenance_lock(
    active: bool,
) -> PlantState:
    """
    Simülatör bakım kilidini açar veya kapatır.
    """

    return sim.set_maintenance_lock(
        active
    )
@app.post(
    "/api/v1/plant/power-setpoint",
    response_model=CommandResult,
)
def set_plant_power_target(
    request: PlantPowerTargetRequest,
) -> CommandResult:
    """
    Tüm HES için toplam MW üretim hedefi gönderir.
    """

    return sim.request_plant_power_target(
        target_power_mw=(
            request.target_power_mw
        )
    )
@app.get(
    "/api/v1/anomalies",
    response_model=list[AnomalyFinding],
)
def get_anomalies() -> list[AnomalyFinding]:
    """
    Mevcut HES state'i üzerinde
    anomaly analizi yapar.
    """

    plant = sim.snapshot()

    return detect_anomalies(
        plant
    )


@app.get(
    "/api/v1/decisions",
    response_model=list[DecisionRecommendation],
)
def get_decisions() -> list[DecisionRecommendation]:
    """
    Alarm + rule anomaly + ML anomaly
    sonuçlarından operatör önerileri üretir.

    Komut yürütmez.
    """

    plant = sim.snapshot()

    alarms = sim.active_alarms()

    rule_anomalies = detect_anomalies(
        plant
    )

    ml_anomalies = (
        evaluate_plant_with_model(
            plant
        )
    )

    return build_decision_recommendations(
        plant=plant,
        alarms=alarms,
        anomalies=rule_anomalies,
        ml_anomalies=ml_anomalies,
    )
@app.get(
    "/api/v1/ml/anomalies",
    response_model=list[MLAnomalyFinding],
)
def get_ml_anomalies() -> list[MLAnomalyFinding]:
    """
    Eğitilmiş IsolationForest modeliyle
    çalışan HES ünitelerini analiz eder.

    Bu endpoint yalnızca analiz yapar.
    Kontrol komutu göndermez.
    """

    plant = sim.snapshot()

    return evaluate_plant_with_model(
        plant
    )
@app.get(
    "/api/v1/system/assessment",
    response_model=SystemAssessment,
)
def get_system_assessment() -> SystemAssessment:
    """
    HES'in alarm, anomaly, ML ve decision
    sonuçlarını tek bir response içinde verir.
    """

    plant = sim.snapshot()

    alarms = sim.active_alarms()

    rule_anomalies = detect_anomalies(
        plant
    )

    ml_anomalies = (
        evaluate_plant_with_model(
            plant
        )
    )

    recommendations = (
        build_decision_recommendations(
            plant=plant,
            alarms=alarms,
            anomalies=rule_anomalies,
            ml_anomalies=ml_anomalies,
        )
    )

    return SystemAssessment(
        simulation_time_s=(
            plant.simulation_time_s
        ),
        total_active_power_mw=(
            total_active_power_mw(
                plant
            )
        ),
        plant_power_target_mw=(
            sim.plant_power_target_mw
        ),
        active_alarms=alarms,
        rule_anomalies=rule_anomalies,
        ml_anomalies=ml_anomalies,
        recommendations=recommendations,
    )
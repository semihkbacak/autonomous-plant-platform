from stage1.api import create_router as create_stage1_router, get_coordinator
from advanced_v2.api import create_router as create_advanced_router, get_controller as get_advanced_controller
from research_v2.api import router as research_v2_router
from app.v14_research_api import create_v14_router
from app.v13_engineering_lab import create_v13_lab_router
from app.site_guard import OperationModeFence, operation_mode
from app.site_readiness import create_site_readiness_router
from app.platform_alarm_center import create_platform_alarm_router
from app.docs_ui import create_docs_router
from app.sim_runtime import SimulatorSessions
from app.live_twins_v20 import create_live_twins_router
from app.sim_console_api import create_sim_console_router
import asyncio
import os
from app.solar_dashboard import router as solar_dashboard_router
from app.hydro_analytics_api import create_hydro_analytics_router
from app.wind_analytics_api import create_wind_analytics_router
from app.platform_dashboard import create_platform_router
from app.solar_inverter_history_api import (
    create_solar_inverter_history_router,
)
from app.hydro_live_api import create_hydro_live_router
from os import getenv
from app.solar_analytics_api import create_solar_analytics_router
from app.solar_mppt_api import (
    create_solar_mppt_router,
)
from app.solar_history_api import create_solar_history_router
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
sim_sessions = SimulatorSessions()


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

        if operation_mode() == 'SIMULATION':
            if sim.auto_tick_enabled:
                sim.tick()
            # GES/RES: accelerated 15-minute synthetic steps, opt-in only.
            await asyncio.to_thread(sim_sessions.auto_step)
            # Explicit Stage-1 portfolio: one single 15-minute slot / 2 wall seconds.
            await asyncio.to_thread(get_coordinator().auto_step)
            # Distinct, opt-in advanced physics portfolio; never controls site hardware.
            await asyncio.to_thread(get_advanced_controller().auto_step)


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

        # A graceful server shutdown must never restart a previously RUNNING
        # synthetic three-plant clock without explicit local user consent.
        try:
            stage1 = get_coordinator()
            if stage1.state == 'RUNNING':
                await asyncio.to_thread(stage1.pause)
        except Exception:
            # A failed pause write is still fail-closed on next startup:
            # RUNNING is recovered as PAUSED_RECOVERED from the journal.
            import logging
            logging.getLogger(__name__).exception('Stage1 safe-stop persistence failed')
        try:
            advanced = get_advanced_controller()
            if advanced.state == 'RUNNING':
                await asyncio.to_thread(advanced.pause)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Advanced research safe-stop failed')


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    docs_url=None,
    title="Autonomous Plant Platform - Simulator",
    version="2.0.0-research-preview",
    description=(
        "Local simulation and offline research preview for a vendor-independent "
        "industrial autonomy platform. "
        "No real PLC/SCADA/OT system is connected. "
        "All process values are synthetic."
    ),
    lifespan=lifespan,
)
# V12 LOCAL SIMULATION/SHADOW BOUNDARY (no physical control)
operation_mode()  # Fail closed for undefined modes, including REAL.
app.add_middleware(OperationModeFence)
app.include_router(create_site_readiness_router(
    os.getenv('APP_SHADOW_DB', os.path.join(os.path.expanduser('~'),
        '.local', 'state', 'autonomous-plant-platform', 'offline_shadow.sqlite3')),
    os.getenv('APP_SITE_EVIDENCE_DIR'),
))
app.include_router(
    create_solar_mppt_router(
        getenv(
            "GES_HISTORIAN_DB",
            "outputs/ges_v04_integrated_demo/historian.sqlite3",
        )
    )
)
app.include_router(
    create_solar_analytics_router(
        os.getenv(
            "GES_HISTORIAN_DB",
            "outputs/ges_v04_stress_final_7d/historian.sqlite3",
        )
    )
)
# GES Historian read-only API
app.include_router(
    create_solar_history_router(
        os.getenv(
            "GES_HISTORIAN_DB",
            "outputs/ges_normal/historian.sqlite3",
        )
    )
)
app.include_router(solar_dashboard_router)
app.include_router(
    create_hydro_live_router(sim)
)
app.include_router(create_sim_console_router(sim_sessions, sim))
app.include_router(create_live_twins_router(sim_sessions, sim))
# Isolated synchronized HES/GES/RES research clock, with its own persistence.
app.include_router(create_stage1_router())
app.include_router(create_advanced_router())
app.include_router(
    create_platform_alarm_router(sim, sim_sessions)
)
app.include_router(
    create_hydro_analytics_router(
        os.getenv(
            "HES_HISTORIAN_DB",
            "outputs/hes_v10/hydro_history.sqlite3",
        )
    )
)
app.include_router(
    create_solar_inverter_history_router(
        os.getenv(
            "GES_HISTORIAN_DB",
            "outputs/ges_normal/historian.sqlite3",
        )
    )
)
# RES historian and unified HES/GES/RES read-only routes.
app.include_router(
    create_wind_analytics_router(
        os.getenv("RES_HISTORIAN_DB", "outputs/res_v10/wind_history.sqlite3")
    )
)
app.include_router(
    create_platform_router(
        hydro_db=os.getenv("HES_HISTORIAN_DB", "outputs/hes_v10/hydro_history.sqlite3"),
        solar_db=os.getenv("GES_HISTORIAN_DB", "outputs/ges_v05_p03_final/historian.sqlite3"),
        wind_db=os.getenv("RES_HISTORIAN_DB", "outputs/res_v10/wind_history.sqlite3"),
    )
)

# ============================================================
# V13 RESEARCH ENGINEERING LAB - READ ONLY
app.include_router(create_v13_lab_router())

# V14 RESEARCH VALIDATION - READ ONLY
app.include_router(create_v14_router())

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

app.include_router(create_docs_router())


# BEGIN AUTONOMOUS-PLANT ENGINEERING V1.1 (ADD-ONLY)
# Simulator-only engineering diagnostics and optional legacy mutation protection.
from app.engineering_api import create_engineering_router
from app.engineering_audit import LocalCommandAuditMiddleware
app.include_router(create_engineering_router(sim, sim_sessions))
app.add_middleware(LocalCommandAuditMiddleware)
# END AUTONOMOUS-PLANT ENGINEERING V1.1 (ADD-ONLY)

# v2 research preview: strictly offline metadata/measurements, not field actuation
app.include_router(research_v2_router)

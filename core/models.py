from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ============================================================
# UNIT STATUS
# ============================================================

class UnitStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAULT = "FAULT"


# ============================================================
# ALARM MODELS
# ============================================================

class AlarmSeverity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlarmEvent(BaseModel):
    """
    O anda aktif olan bir alarmı temsil eder.
    """

    code: str
    severity: AlarmSeverity
    message: str
    unit_id: str | None = None


class AlarmHistoryEntry(BaseModel):
    """
    Daha önce oluşmuş bir alarmın geçmiş kaydı.
    """

    code: str
    severity: AlarmSeverity
    message: str
    unit_id: str | None = None

    # Alarmın ilk görüldüğü simülasyon zamanı.
    first_seen_simulation_time_s: float


# ============================================================
# UNIT STATE
# ============================================================

class UnitState(BaseModel):
    """
    Bir hidroelektrik üretim ünitesinin mevcut durumunu temsil eder.

    Bütün değerler simülatör/demo verileridir.
    """

    # --------------------------------------------------------
    # Kimlik ve nominal güç
    # --------------------------------------------------------

    unit_id: str

    rated_power_mw: float = Field(
        gt=0,
    )

    status: UnitStatus = UnitStatus.STOPPED

    # --------------------------------------------------------
    # Elektriksel değerler
    # --------------------------------------------------------

    active_power_mw: float = 0.0

    reactive_power_mvar: float = 0.0

    voltage_kv: float = 0.0

    current_a: float = 0.0

    frequency_hz: float = 0.0

    # --------------------------------------------------------
    # Mekanik / proses değerleri
    # --------------------------------------------------------

    rpm: float = 0.0

    flow_m3_s: float = 0.0

    bearing_temperature_c: float = 25.0

    generator_temperature_c: float = 25.0

    vibration_mm_s: float = 0.0

    # --------------------------------------------------------
    # Safety durumu
    # --------------------------------------------------------

    ready: bool = True

    fault: bool = False

    # --------------------------------------------------------
    # Hidroelektrik verim değerleri
    # --------------------------------------------------------

    turbine_efficiency: float = Field(
        default=0.90,
        gt=0,
        le=1,
    )

    generator_efficiency: float = Field(
        default=0.97,
        gt=0,
        le=1,
    )

    # --------------------------------------------------------
    # Pelton türbini / nozzle modeli
    # --------------------------------------------------------

    needle_opening_pct: float = Field(
        default=0.0,
        ge=0,
        le=100,
    )

    nozzle_diameter_m: float = Field(
        default=0.16,
        gt=0,
    )

    nozzle_discharge_coefficient: float = Field(
        default=0.98,
        gt=0,
        le=1,
    )

    jet_count: int = Field(
        default=4,
        ge=1,
    )

    # --------------------------------------------------------
    # Governor
    # --------------------------------------------------------

    # Governor'ın o anda takip ettiği hedef güç.
    governor_target_power_mw: float = Field(
        default=0.0,
        ge=0,
    )

    # Operatör veya scheduler tarafından verilen güç hedefi.
    #
    # None:
    # Dışarıdan özel bir güç hedefi verilmemiş.
    #
    # Örnek:
    # 8.0 -> ünite 8 MW hedefini takip eder.
    power_setpoint_mw: float | None = Field(
        default=None,
        ge=0,
    )


# ============================================================
# PLANT STATE
# ============================================================

class PlantState(BaseModel):
    """
    Tüm HES tesisinin mevcut durumunu temsil eder.
    """

    plant_id: str = "DEMO_HES"

    plant_type: str = "hydro"

    mode: str = "MANUAL"

    # --------------------------------------------------------
    # Tesis güvenlik / işletme durumu
    # --------------------------------------------------------

    grid_available: bool = True

    emergency_stop: bool = False

    maintenance_lock: bool = False

    # --------------------------------------------------------
    # Su / düşü değerleri
    # --------------------------------------------------------

    headpond_level_pct: float = Field(
        default=80.0,
        ge=0,
        le=100,
    )

    gross_head_m: float = Field(
        default=310.0,
        gt=0,
    )

    hydraulic_loss_m: float = Field(
        default=10.0,
        ge=0,
    )

    net_head_m: float = Field(
        default=300.0,
        ge=0,
    )

    # --------------------------------------------------------
    # Simülasyon zamanı
    # --------------------------------------------------------

    simulation_time_s: float = Field(
        default=0.0,
        ge=0,
    )

    # --------------------------------------------------------
    # Üniteler
    # --------------------------------------------------------

    units: list[UnitState] = Field(
        default_factory=list,
    )


# ============================================================
# COMMAND RESULT
# ============================================================

class CommandResult(BaseModel):
    """
    START, STOP veya power-setpoint gibi
    komutların sonucunu temsil eder.
    """

    accepted: bool

    message: str

    unit_id: str | None = None


# ============================================================
# SIMULATOR RUNTIME STATUS
# ============================================================

class RuntimeStatus(BaseModel):
    """
    Dijital ikizin çalışma durumunu temsil eder.
    """

    auto_tick_enabled: bool

    interval_seconds: float

    simulation_time_s: float
class DecisionPriority(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AnomalyFinding(BaseModel):
    """
    Anomali analiz katmanının bulduğu olağandışı durumu temsil eder.
    """

    code: str

    severity: AlarmSeverity

    score: float = Field(
        ge=0,
        le=1,
    )

    message: str

    unit_id: str | None = None


class DecisionRecommendation(BaseModel):
    """
    Decision Engine tarafından operatöre sunulan öneri.

    Bu model kendi başına PLC/SCADA komutu göndermez.
    """

    action: str

    priority: DecisionPriority

    reason: str

    unit_id: str | None = None
class MLAnomalyFinding(BaseModel):
    """
    Makine öğrenmesi modelinin
    bir ünite için ürettiği anomaly sonucu.
    """

    unit_id: str

    is_anomaly: bool

    anomaly_score: float = Field(
        ge=0,
        le=1,
    )

    model_name: str = "IsolationForest"
class SystemAssessment(BaseModel):
    """
    HES'in tek noktadan genel durum değerlendirmesi.
    """

    simulation_time_s: float

    total_active_power_mw: float

    plant_power_target_mw: float | None = None

    active_alarms: list[AlarmEvent] = Field(
        default_factory=list,
    )

    rule_anomalies: list[AnomalyFinding] = Field(
        default_factory=list,
    )

    ml_anomalies: list[MLAnomalyFinding] = Field(
        default_factory=list,
    )

    recommendations: list[DecisionRecommendation] = Field(
        default_factory=list,
    )
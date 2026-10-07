from __future__ import annotations

from copy import deepcopy
from math import sin, sqrt
from threading import RLock

from core.alarms import detect_alarms
from core.governor import (
    calculate_governor_correction_pct,
    calculate_power_error_mw,
)
from core.models import (
    AlarmEvent,
    AlarmHistoryEntry,
    CommandResult,
    PlantState,
    RuntimeStatus,
    UnitState,
    UnitStatus,
)
from core.safety import (
    plant_power_target_permitted,
    power_setpoint_permitted,
    start_permitted,
)
from core.scheduler import (
    calculate_dispatch_setpoints,
    select_units_for_target,
)
from simulator.hydro_physics import (
    calculate_hydro_power_mw,
    calculate_net_head_m,
    calculate_pelton_flow_m3_s,
    calculate_required_needle_opening_pct,
    move_toward_target,
)
from simulator.scenarios import (
    ScenarioType,
    apply_plant_scenario,
)


class HydroPlantSimulator:
    """
    HES için sentetik dijital ikiz.

    Bu sınıf gerçek PLC, SCADA, RTU,
    protection relay veya saha cihazına bağlanmaz.

    Tüm değerler demo/simülasyon amaçlıdır.
    """

    # Needle bir tick içerisinde en fazla
    # 5 yüzde puan hareket edebilir.
    MAX_NEEDLE_STEP_PCT_PER_TICK = 5.0

    # Otomatik simülasyon güncelleme süresi.
    AUTO_TICK_INTERVAL_S = 1.0

    # Demo jeneratör gerilimi.
    DEMO_VOLTAGE_KV = 10.5

    # Demo senkron devir.
    DEMO_SYNCHRONOUS_RPM = 750.0

    def __init__(self) -> None:
        self._lock = RLock()

        # ====================================================
        # PLANT STATE
        # ====================================================

        self.state = PlantState(
            units=[
                UnitState(
                    unit_id="UNIT_1",
                    rated_power_mw=15.0,
                ),
                UnitState(
                    unit_id="UNIT_2",
                    rated_power_mw=15.0,
                ),
            ]
        )

        # START işleminin kaç tick ilerlediğini tutar.
        self._start_progress: dict[str, int] = {
            "UNIT_1": 0,
            "UNIT_2": 0,
        }

        # STOP işleminin kaç tick ilerlediğini tutar.
        self._stop_progress: dict[str, int] = {
            "UNIT_1": 0,
            "UNIT_2": 0,
        }

        # Otomatik tick açık mı?
        self.auto_tick_enabled = True

        # ====================================================
        # PLANT POWER TARGET
        # ====================================================

        # Tesisin toplam üretim hedefi.
        #
        # None:
        # Scheduler tarafından tesis hedefi verilmedi.
        #
        # Örnek:
        # 20.0 -> tesis toplam 20 MW üretmeye çalışır.
        self.plant_power_target_mw: float | None = None

        # ====================================================
        # ALARM HISTORY
        # ====================================================

        # Daha önce oluşmuş alarm kayıtları.
        self._alarm_history: list[
            AlarmHistoryEntry
        ] = []

        # Bir önceki kontrolde aktif olan
        # alarm anahtarları.
        #
        # Böylece aynı alarm her tick'te
        # tekrar tekrar history'ye yazılmaz.
        self._active_alarm_keys: set[
            tuple[str, str | None]
        ] = set()

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self) -> PlantState:
        """
        Tesisin mevcut durumunun güvenli bir
        kopyasını döndürür.
        """

        with self._lock:
            return deepcopy(self.state)

    # ========================================================
    # SIMULATOR RUNTIME
    # ========================================================

    def runtime_status(self) -> RuntimeStatus:
        """
        Simülatörün çalışma durumunu döndürür.
        """

        with self._lock:
            return RuntimeStatus(
                auto_tick_enabled=self.auto_tick_enabled,
                interval_seconds=(
                    self.AUTO_TICK_INTERVAL_S
                ),
                simulation_time_s=(
                    self.state.simulation_time_s
                ),
            )

    def set_auto_tick(
        self,
        active: bool,
    ) -> RuntimeStatus:
        """
        Otomatik tick özelliğini açar/kapatır.
        """

        with self._lock:
            self.auto_tick_enabled = active

            return self.runtime_status()

    # ========================================================
    # UNIT LOOKUP
    # ========================================================

    def _get_unit(
        self,
        unit_id: str,
    ) -> UnitState | None:
        """
        UNIT_1 gibi verilen ID'ye göre
        ilgili üniteyi bulur.
        """

        return next(
            (
                unit
                for unit in self.state.units
                if unit.unit_id == unit_id
            ),
            None,
        )

    # ========================================================
    # ALARMS
    # ========================================================

    def active_alarms(
        self,
    ) -> list[AlarmEvent]:
        """
        O anda aktif olan alarmları döndürür.
        """

        with self._lock:
            return detect_alarms(
                self.state
            )

    def alarm_history(
        self,
    ) -> list[AlarmHistoryEntry]:
        """
        Alarm geçmişinin güvenli kopyasını döndürür.
        """

        with self._lock:
            return deepcopy(
                self._alarm_history
            )

    def _update_alarm_history(
        self,
    ) -> None:
        """
        Yeni oluşan alarmları history'ye kaydeder.

        Alarm zaten aktifse tekrar kaydetmez.
        """

        current_alarms = detect_alarms(
            self.state
        )

        current_keys = {
            (
                alarm.code,
                alarm.unit_id,
            )
            for alarm in current_alarms
        }

        for alarm in current_alarms:
            key = (
                alarm.code,
                alarm.unit_id,
            )

            # Alarm önceki kontrolde yoksa
            # yeni alarm olarak history'ye ekle.
            if (
                key
                not in self._active_alarm_keys
            ):
                self._alarm_history.append(
                    AlarmHistoryEntry(
                        code=alarm.code,
                        severity=alarm.severity,
                        message=alarm.message,
                        unit_id=alarm.unit_id,
                        first_seen_simulation_time_s=(
                            self.state.simulation_time_s
                        ),
                    )
                )

        # Bir sonraki kontrol için
        # aktif alarm setini güncelle.
        self._active_alarm_keys = (
            current_keys
        )

    # ========================================================
    # UNIT START
    # ========================================================

    def request_start(
        self,
        unit_id: str,
    ) -> CommandResult:
        """
        Bir ünitenin çalıştırılması için
        START talebi işler.
        """

        with self._lock:
            unit = self._get_unit(
                unit_id
            )

            if unit is None:
                return CommandResult(
                    accepted=False,
                    message="Unknown unit",
                    unit_id=unit_id,
                )

            if unit.status in {
                UnitStatus.STARTING,
                UnitStatus.RUNNING,
            }:
                return CommandResult(
                    accepted=False,
                    message=(
                        f"{unit_id} is already "
                        f"{unit.status}"
                    ),
                    unit_id=unit_id,
                )

            # START talebi Safety Engine'den geçer.
            allowed, reasons = (
                start_permitted(
                    self.state,
                    unit,
                )
            )

            if not allowed:
                return CommandResult(
                    accepted=False,
                    message=(
                        "Start blocked: "
                        + "; ".join(reasons)
                    ),
                    unit_id=unit_id,
                )

            unit.status = (
                UnitStatus.STARTING
            )

            unit.active_power_mw = 0.0

            self._start_progress[
                unit_id
            ] = 0

            return CommandResult(
                accepted=True,
                message=(
                    "Simulator start sequence "
                    "initiated"
                ),
                unit_id=unit_id,
            )

    # ========================================================
    # UNIT STOP
    # ========================================================

    def request_stop(
        self,
        unit_id: str,
    ) -> CommandResult:
        """
        Bir ünitenin durdurulması için
        STOP talebi işler.
        """

        with self._lock:
            unit = self._get_unit(
                unit_id
            )

            if unit is None:
                return CommandResult(
                    accepted=False,
                    message="Unknown unit",
                    unit_id=unit_id,
                )

            if unit.status in {
                UnitStatus.STOPPED,
                UnitStatus.STOPPING,
            }:
                return CommandResult(
                    accepted=False,
                    message=(
                        f"{unit_id} is already "
                        f"{unit.status}"
                    ),
                    unit_id=unit_id,
                )

            unit.status = (
                UnitStatus.STOPPING
            )

            self._stop_progress[
                unit_id
            ] = 0

            return CommandResult(
                accepted=True,
                message=(
                    "Simulator stop sequence "
                    "initiated"
                ),
                unit_id=unit_id,
            )

    # ========================================================
    # UNIT POWER SETPOINT
    # ========================================================

    def request_power_setpoint(
        self,
        unit_id: str,
        target_power_mw: float,
    ) -> CommandResult:
        """
        Operatör veya scheduler tarafından gelen
        ünite güç hedefini işler.
        """

        with self._lock:
            unit = self._get_unit(
                unit_id
            )

            if unit is None:
                return CommandResult(
                    accepted=False,
                    message="Unknown unit",
                    unit_id=unit_id,
                )

            # Güç hedefi Safety Engine'den geçer.
            allowed, reasons = (
                power_setpoint_permitted(
                    self.state,
                    unit,
                    target_power_mw,
                )
            )

            if not allowed:
                return CommandResult(
                    accepted=False,
                    message=(
                        "Power setpoint blocked: "
                        + "; ".join(reasons)
                    ),
                    unit_id=unit_id,
                )

            unit.power_setpoint_mw = (
                target_power_mw
            )

            return CommandResult(
                accepted=True,
                message=(
                    "Power setpoint accepted"
                ),
                unit_id=unit_id,
            )

    # ========================================================
    # PLANT POWER TARGET
    # ========================================================

    def request_plant_power_target(
        self,
        target_power_mw: float,
    ) -> CommandResult:
        """
        Tüm HES için toplam üretim hedefi alır.

        Örnek:
        target_power_mw = 20

        Scheduler gerekli üniteleri seçer
        ve toplam hedefi dağıtır.
        """

        with self._lock:
            allowed, reasons = (
                plant_power_target_permitted(
                    self.state,
                    target_power_mw,
                )
            )

            if not allowed:
                return CommandResult(
                    accepted=False,
                    message=(
                        "Plant power target blocked: "
                        + "; ".join(reasons)
                    ),
                    unit_id=None,
                )

            self.plant_power_target_mw = (
                target_power_mw
            )

            return CommandResult(
                accepted=True,
                message=(
                    "Plant power target accepted"
                ),
                unit_id=None,
            )

    # ========================================================
    # PLANT DISPATCH
    # ========================================================

    def _apply_plant_dispatch(
        self,
    ) -> None:
        """
        Tesis toplam güç hedefini ünitelere dağıtır.

        Örnek:

        UNIT_1 = 15 MW
        UNIT_2 = 15 MW

        Tesis hedefi = 20 MW

        Scheduler:
            UNIT_1 + UNIT_2

        Setpoint:
            UNIT_1 = 10 MW
            UNIT_2 = 10 MW
        """

        # Tesis hedefi yoksa
        # scheduler hiçbir şey yapmaz.
        if (
            self.plant_power_target_mw
            is None
        ):
            return

        # Hedef için gerekli minimum
        # üniteleri seç.
        selected_unit_ids = (
            select_units_for_target(
                self.state,
                self.plant_power_target_mw,
            )
        )

        # Toplam hedefi seçilen ünitelere dağıt.
        setpoints = (
            calculate_dispatch_setpoints(
                self.state,
                self.plant_power_target_mw,
                selected_unit_ids,
            )
        )

        selected_set = set(
            selected_unit_ids
        )

        for unit in self.state.units:

            # -----------------------------------------------
            # Ünite üretim için seçildiyse
            # -----------------------------------------------

            if (
                unit.unit_id
                in selected_set
            ):

                # STOPPED üniteyse önce START ver.
                if (
                    unit.status
                    == UnitStatus.STOPPED
                ):
                    self.request_start(
                        unit.unit_id
                    )

                # RUNNING hale geldiyse
                # MW setpoint ver.
                elif (
                    unit.status
                    == UnitStatus.RUNNING
                ):
                    self.request_power_setpoint(
                        unit_id=unit.unit_id,
                        target_power_mw=(
                            setpoints[
                                unit.unit_id
                            ]
                        ),
                    )

            # -----------------------------------------------
            # Ünite artık gerekli değilse
            # -----------------------------------------------

            else:
                if unit.status in {
                    UnitStatus.RUNNING,
                    UnitStatus.STARTING,
                }:
                    self.request_stop(
                        unit.unit_id
                    )

    # ========================================================
    # SIMULATION SCENARIO
    # ========================================================

    def apply_scenario(
        self,
        scenario: ScenarioType,
        seed: int | None = None,
    ) -> PlantState:
        """
        Dijital ikize sentetik test senaryosu uygular.

        Örnek:
        GRID_LOSS
        UNIT_FAULT
        HIGH_TEMPERATURE
        HIGH_VIBRATION

        Gerçek PLC/SCADA bağlantısı yoktur.
        """

        with self._lock:
            self.state = (
                apply_plant_scenario(
                    plant=self.state,
                    scenario=scenario,
                    seed=seed,
                )
            )

            # Senaryo sonucunda alarm oluşmuş olabilir.
            self._update_alarm_history()

            return deepcopy(
                self.state
            )

    # ========================================================
    # MAIN SIMULATION TICK
    # ========================================================

    def tick(
        self,
    ) -> PlantState:
        """
        Dijital ikizi bir simülasyon adımı ilerletir.
        """

        with self._lock:

            # Simülasyon zamanını 1 saniye ilerlet.
            self.state.simulation_time_s += 1

            t = (
                self.state.simulation_time_s
            )

            # =================================================
            # NET HEAD
            # =================================================

            self.state.net_head_m = (
                calculate_net_head_m(
                    gross_head_m=(
                        self.state.gross_head_m
                    ),
                    hydraulic_loss_m=(
                        self.state.hydraulic_loss_m
                    ),
                )
            )

            # =================================================
            # PLANT SCHEDULER / DISPATCH
            # =================================================

            self._apply_plant_dispatch()

            # =================================================
            # UNIT STATE MACHINE
            # =================================================

            for index, unit in enumerate(
                self.state.units
            ):
                phase = (
                    index
                    * 1.4
                )

                # =============================================
                # STARTING
                # =============================================

                if (
                    unit.status
                    == UnitStatus.STARTING
                ):
                    self._start_progress[
                        unit.unit_id
                    ] += 1

                    progress = (
                        self._start_progress[
                            unit.unit_id
                        ]
                    )

                    fraction = min(
                        progress / 4.0,
                        1.0,
                    )

                    unit.rpm = (
                        self.DEMO_SYNCHRONOUS_RPM
                        * fraction
                    )

                    unit.voltage_kv = (
                        self.DEMO_VOLTAGE_KV
                        * fraction
                    )

                    unit.frequency_hz = (
                        50.0
                        * fraction
                    )

                    unit.active_power_mw = (
                        unit.rated_power_mw
                        * 0.8
                        * fraction
                    )

                    unit.reactive_power_mvar = (
                        unit.active_power_mw
                        * 0.12
                    )

                    # STARTING kısmında
                    # basitleştirilmiş sentetik debi.
                    unit.flow_m3_s = (
                        0.22
                        * unit.active_power_mw
                    )

                    unit.bearing_temperature_c = (
                        min(
                            unit.bearing_temperature_c
                            + 1.2,
                            55.0,
                        )
                    )

                    unit.generator_temperature_c = (
                        min(
                            unit.generator_temperature_c
                            + 1.6,
                            62.0,
                        )
                    )

                    unit.vibration_mm_s = min(
                        unit.vibration_mm_s
                        + 0.25,
                        2.2,
                    )

                    # START dizisi tamamlandı.
                    if progress >= 4:
                        unit.governor_target_power_mw = (
                            unit.active_power_mw
                        )

                        unit.needle_opening_pct = (
                            calculate_required_needle_opening_pct(
                                target_power_mw=(
                                    unit.active_power_mw
                                ),
                                net_head_m=(
                                    self.state.net_head_m
                                ),
                                nozzle_diameter_m=(
                                    unit.nozzle_diameter_m
                                ),
                                discharge_coefficient=(
                                    unit.nozzle_discharge_coefficient
                                ),
                                jet_count=(
                                    unit.jet_count
                                ),
                                turbine_efficiency=(
                                    unit.turbine_efficiency
                                ),
                                generator_efficiency=(
                                    unit.generator_efficiency
                                ),
                            )
                        )

                        unit.status = (
                            UnitStatus.RUNNING
                        )

                # =============================================
                # RUNNING
                # =============================================

                elif (
                    unit.status
                    == UnitStatus.RUNNING
                ):

                    ripple = (
                        0.18
                        * sin(
                            (t / 5.0)
                            + phase
                        )
                    )

                    # -----------------------------------------
                    # POWER TARGET
                    # -----------------------------------------

                    if (
                        unit.power_setpoint_mw
                        is None
                    ):
                        # Dışarıdan hedef verilmediyse
                        # eski demo üretimi.
                        target_unit_power_mw = max(
                            0.0,
                            min(
                                unit.rated_power_mw,
                                (
                                    unit.rated_power_mw
                                    * 0.8
                                    + ripple
                                ),
                            ),
                        )

                    else:
                        # Operatör veya scheduler hedefi.
                        target_unit_power_mw = min(
                            unit.power_setpoint_mw,
                            unit.rated_power_mw,
                        )

                    unit.governor_target_power_mw = (
                        target_unit_power_mw
                    )

                    # -----------------------------------------
                    # GOVERNOR FEEDFORWARD
                    # -----------------------------------------

                    target_needle_opening_pct = (
                        calculate_required_needle_opening_pct(
                            target_power_mw=(
                                unit.governor_target_power_mw
                            ),
                            net_head_m=(
                                self.state.net_head_m
                            ),
                            nozzle_diameter_m=(
                                unit.nozzle_diameter_m
                            ),
                            discharge_coefficient=(
                                unit.nozzle_discharge_coefficient
                            ),
                            jet_count=(
                                unit.jet_count
                            ),
                            turbine_efficiency=(
                                unit.turbine_efficiency
                            ),
                            generator_efficiency=(
                                unit.generator_efficiency
                            ),
                        )
                    )

                    # -----------------------------------------
                    # GOVERNOR FEEDBACK
                    # -----------------------------------------

                    power_error_mw = (
                        calculate_power_error_mw(
                            target_power_mw=(
                                unit.governor_target_power_mw
                            ),
                            actual_power_mw=(
                                unit.active_power_mw
                            ),
                        )
                    )

                    correction_pct = (
                        calculate_governor_correction_pct(
                            power_error_mw=(
                                power_error_mw
                            ),
                            kp=2.0,
                        )
                    )

                    # Demo P-controller düzeltmesini sınırla.
                    correction_pct = max(
                        -10.0,
                        min(
                            10.0,
                            correction_pct,
                        ),
                    )

                    # Feedforward + feedback.
                    target_needle_opening_pct = (
                        max(
                            0.0,
                            min(
                                100.0,
                                (
                                    target_needle_opening_pct
                                    + correction_pct
                                ),
                            ),
                        )
                    )

                    # -----------------------------------------
                    # NEEDLE ACTUATOR
                    # -----------------------------------------

                    unit.needle_opening_pct = (
                        move_toward_target(
                            current_value=(
                                unit.needle_opening_pct
                            ),
                            target_value=(
                                target_needle_opening_pct
                            ),
                            max_step=(
                                self.MAX_NEEDLE_STEP_PCT_PER_TICK
                            ),
                        )
                    )

                    # -----------------------------------------
                    # PELTON FLOW
                    # -----------------------------------------

                    unit.flow_m3_s = (
                        calculate_pelton_flow_m3_s(
                            net_head_m=(
                                self.state.net_head_m
                            ),
                            needle_opening_pct=(
                                unit.needle_opening_pct
                            ),
                            nozzle_diameter_m=(
                                unit.nozzle_diameter_m
                            ),
                            discharge_coefficient=(
                                unit.nozzle_discharge_coefficient
                            ),
                            jet_count=(
                                unit.jet_count
                            ),
                        )
                    )

                    # -----------------------------------------
                    # HYDRO POWER
                    # -----------------------------------------

                    unit.active_power_mw = (
                        calculate_hydro_power_mw(
                            flow_m3_s=(
                                unit.flow_m3_s
                            ),
                            net_head_m=(
                                self.state.net_head_m
                            ),
                            turbine_efficiency=(
                                unit.turbine_efficiency
                            ),
                            generator_efficiency=(
                                unit.generator_efficiency
                            ),
                        )
                    )

                    # -----------------------------------------
                    # ELECTRICAL / MECHANICAL DEMO SIGNALS
                    # -----------------------------------------

                    unit.reactive_power_mvar = max(
                        0.0,
                        (
                            unit.active_power_mw
                            * 0.12
                            + 0.03
                            * sin(
                                (t / 7.0)
                                + phase
                            )
                        ),
                    )

                    unit.voltage_kv = (
                        self.DEMO_VOLTAGE_KV
                        + 0.02
                        * sin(
                            (t / 8.0)
                            + phase
                        )
                    )

                    unit.frequency_hz = (
                        50.0
                        + 0.01
                        * sin(
                            (t / 6.0)
                            + phase
                        )
                    )

                    unit.rpm = (
                        self.DEMO_SYNCHRONOUS_RPM
                        + 0.3
                        * sin(
                            (t / 5.5)
                            + phase
                        )
                    )

                    unit.bearing_temperature_c = (
                        min(
                            62.0,
                            (
                                unit.bearing_temperature_c
                                + 0.08
                            ),
                        )
                    )

                    unit.generator_temperature_c = (
                        min(
                            72.0,
                            (
                                unit.generator_temperature_c
                                + 0.11
                            ),
                        )
                    )

                    unit.vibration_mm_s = max(
                        0.0,
                        (
                            1.0
                            + 0.08
                            * sin(
                                (t / 4.0)
                                + phase
                            )
                        ),
                    )

                # =============================================
                # STOPPING
                # =============================================

                elif (
                    unit.status
                    == UnitStatus.STOPPING
                ):
                    self._stop_progress[
                        unit.unit_id
                    ] += 1

                    progress = (
                        self._stop_progress[
                            unit.unit_id
                        ]
                    )

                    decay = max(
                        0.0,
                        (
                            1.0
                            - progress / 3.0
                        ),
                    )

                    unit.active_power_mw *= (
                        decay
                    )

                    unit.reactive_power_mvar *= (
                        decay
                    )

                    unit.voltage_kv = (
                        self.DEMO_VOLTAGE_KV
                        * decay
                    )

                    unit.frequency_hz = (
                        50.0
                        * decay
                    )

                    unit.rpm = (
                        self.DEMO_SYNCHRONOUS_RPM
                        * decay
                    )

                    unit.flow_m3_s *= (
                        decay
                    )

                    unit.bearing_temperature_c = (
                        max(
                            30.0,
                            (
                                unit.bearing_temperature_c
                                - 0.8
                            ),
                        )
                    )

                    unit.generator_temperature_c = (
                        max(
                            30.0,
                            (
                                unit.generator_temperature_c
                                - 1.0
                            ),
                        )
                    )

                    unit.vibration_mm_s = max(
                        0.0,
                        (
                            unit.vibration_mm_s
                            - 0.35
                        ),
                    )

                    if progress >= 3:
                        unit.status = (
                            UnitStatus.STOPPED
                        )

                        self._zero_electrical_and_mechanical_signals(
                            unit
                        )

                # =============================================
                # STOPPED
                # =============================================

                elif (
                    unit.status
                    == UnitStatus.STOPPED
                ):
                    self._zero_electrical_and_mechanical_signals(
                        unit
                    )

                    unit.bearing_temperature_c = (
                        max(
                            25.0,
                            (
                                unit.bearing_temperature_c
                                - 0.25
                            ),
                        )
                    )

                    unit.generator_temperature_c = (
                        max(
                            25.0,
                            (
                                unit.generator_temperature_c
                                - 0.3
                            ),
                        )
                    )

                    unit.vibration_mm_s = 0.0

                # =============================================
                # CURRENT ESTIMATE
                # =============================================

                if (
                    unit.active_power_mw > 0
                    and unit.voltage_kv > 0
                ):
                    apparent_power_mva = sqrt(
                        unit.active_power_mw**2
                        + unit.reactive_power_mvar**2
                    )

                    unit.current_a = (
                        apparent_power_mva
                        * 1_000.0
                    ) / (
                        sqrt(3.0)
                        * unit.voltage_kv
                    )

                else:
                    unit.current_a = 0.0

            # =================================================
            # PLANT TOTAL POWER
            # =================================================

            total_power = sum(
                unit.active_power_mw
                for unit in self.state.units
            )

            # Basitleştirilmiş headpond tüketimi.
            self.state.headpond_level_pct = (
                max(
                    0.0,
                    (
                        self.state.headpond_level_pct
                        - 0.0025
                        * total_power
                    ),
                )
            )

            # =================================================
            # ALARM HISTORY UPDATE
            # =================================================

            self._update_alarm_history()

            return deepcopy(
                self.state
            )

    # ========================================================
    # ZERO SIGNALS
    # ========================================================

    @staticmethod
    def _zero_electrical_and_mechanical_signals(
        unit: UnitState,
    ) -> None:
        """
        Ünite STOPPED olduğunda elektriksel ve
        mekanik çıkışları sıfırlar.
        """

        unit.active_power_mw = 0.0
        unit.reactive_power_mvar = 0.0
        unit.voltage_kv = 0.0
        unit.current_a = 0.0
        unit.frequency_hz = 0.0
        unit.rpm = 0.0
        unit.flow_m3_s = 0.0

    # ========================================================
    # EMERGENCY STOP
    # ========================================================

    def set_emergency_stop(
        self,
        active: bool,
    ) -> PlantState:
        """
        Simülatör emergency-stop durumunu değiştirir.
        """

        with self._lock:
            self.state.emergency_stop = (
                active
            )

            if active:
                for unit in self.state.units:
                    if unit.status in {
                        UnitStatus.RUNNING,
                        UnitStatus.STARTING,
                    }:
                        unit.status = (
                            UnitStatus.STOPPING
                        )

                        self._stop_progress[
                            unit.unit_id
                        ] = 0

            self._update_alarm_history()

            return deepcopy(
                self.state
            )

    # ========================================================
    # MAINTENANCE LOCK
    # ========================================================

    def set_maintenance_lock(
        self,
        active: bool,
    ) -> PlantState:
        """
        Simülatör bakım kilidini açar/kapatır.
        """

        with self._lock:
            self.state.maintenance_lock = (
                active
            )

            self._update_alarm_history()

            return deepcopy(
                self.state
            )
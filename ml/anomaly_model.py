from __future__ import annotations

from functools import lru_cache
from math import exp
from pathlib import Path
from random import Random

from joblib import dump, load
from sklearn.ensemble import IsolationForest

from core.models import (
    MLAnomalyFinding,
    PlantState,
    UnitState,
    UnitStatus,
)


# ============================================================
# MODEL CONFIGURATION
# ============================================================

MODEL_NAME = "IsolationForest"

# Demo calibration threshold.
# anomaly_score gerçek bir olasılık değildir.
# Gerçek tesiste bu eşik saha verileriyle kalibre edilmelidir.
ANOMALY_RISK_THRESHOLD = 0.55
MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "hes_anomaly_iforest.joblib"
)


FEATURE_NAMES = [
    "bearing_temperature_c",
    "generator_temperature_c",
    "vibration_mm_s",
    "frequency_hz",
    "rpm",
    "active_power_fraction",
]


# ============================================================
# FEATURE EXTRACTION
# ============================================================

def extract_unit_features(
    unit: UnitState,
) -> list[float]:
    """
    Ünitenin mevcut sensör değerlerini
    ML modelinin kullanacağı feature
    vektörüne dönüştürür.
    """

    if unit.rated_power_mw > 0:
        active_power_fraction = (
            unit.active_power_mw
            / unit.rated_power_mw
        )
    else:
        active_power_fraction = 0.0

    return [
        unit.bearing_temperature_c,
        unit.generator_temperature_c,
        unit.vibration_mm_s,
        unit.frequency_hz,
        unit.rpm,
        active_power_fraction,
    ]


# ============================================================
# SYNTHETIC TRAINING DATA
# ============================================================

def generate_normal_training_rows(
    count: int = 2000,
    seed: int = 42,
) -> list[list[float]]:
    """
    Normal HES çalışmasını temsil eden
    sentetik eğitim verisi üretir.

    Gerçek tesis veya OEM verisi değildir.
    """

    rng = Random(seed)

    rows: list[list[float]] = []

    for _ in range(count):

        active_power_fraction = rng.uniform(
            0.30,
            0.95,
        )

        bearing_temperature_c = rng.gauss(
            46.0,
            5.0,
        )

        generator_temperature_c = rng.gauss(
            55.0,
            6.0,
        )

        vibration_mm_s = max(
            0.2,
            rng.gauss(
                1.0,
                0.22,
            ),
        )

        frequency_hz = rng.gauss(
            50.0,
            0.015,
        )

        rpm = rng.gauss(
            750.0,
            0.8,
        )

        rows.append(
            [
                bearing_temperature_c,
                generator_temperature_c,
                vibration_mm_s,
                frequency_hz,
                rpm,
                active_power_fraction,
            ]
        )

    return rows


# ============================================================
# TRAIN MODEL
# ============================================================

def train_demo_anomaly_model(
    seed: int = 42,
) -> IsolationForest:
    """
    IsolationForest modelini
    sentetik normal HES verisiyle eğitir.
    """

    training_rows = (
        generate_normal_training_rows(
            count=2000,
            seed=seed,
        )
    )

    model = IsolationForest(
        n_estimators=200,
        contamination=0.03,
        random_state=seed,
    )

    model.fit(
        training_rows
    )

    return model


# ============================================================
# SAVE MODEL
# ============================================================

def save_demo_anomaly_model(
    path: Path = MODEL_PATH,
) -> Path:
    """
    Eğitilmiş modeli models klasörüne kaydeder.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    model = train_demo_anomaly_model()

    dump(
        model,
        path,
    )

    # Cache'deki eski modeli temizle.
    get_anomaly_model.cache_clear()

    return path


# ============================================================
# LOAD MODEL
# ============================================================

@lru_cache(maxsize=1)
def get_anomaly_model() -> IsolationForest:
    """
    Kaydedilmiş model varsa diskten yükler.

    Model henüz oluşturulmamışsa
    bellekte demo model eğitir.
    """

    if MODEL_PATH.exists():
        return load(
            MODEL_PATH
        )

    return train_demo_anomaly_model()


# ============================================================
# RISK SCORE
# ============================================================

def decision_score_to_risk(
    decision_score: float,
) -> float:
    """
    IsolationForest decision score'unu
    0 ile 1 arasında risk skoruna çevirir.

    0 -> düşük anomaly riski
    1 -> yüksek anomaly riski
    """

    risk = 1.0 / (
        1.0
        + exp(
            12.0
            * decision_score
        )
    )

    return max(
        0.0,
        min(
            1.0,
            risk,
        ),
    )


# ============================================================
# SINGLE UNIT INFERENCE
# ============================================================

def evaluate_unit_with_model(
    unit: UnitState,
    model: IsolationForest,
) -> MLAnomalyFinding:
    """
    Tek bir HES ünitesini ML modeliyle analiz eder.

    IsolationForest prediction sonucu ile birlikte
    demo risk eşiği kullanılır. Böylece sınırdaki
    normal çalışma noktalarının false-positive
    üretmesi azaltılır.
    """

    features = extract_unit_features(
        unit
    )

    prediction = int(
        model.predict(
            [features]
        )[0]
    )

    decision_score = float(
        model.decision_function(
            [features]
        )[0]
    )

    anomaly_score = (
        decision_score_to_risk(
            decision_score
        )
    )

    is_anomaly = (
        prediction == -1
        and anomaly_score
        >= ANOMALY_RISK_THRESHOLD
    )

    return MLAnomalyFinding(
        unit_id=unit.unit_id,
        is_anomaly=is_anomaly,
        anomaly_score=anomaly_score,
        model_name=MODEL_NAME,
    )

# ============================================================
# PLANT INFERENCE
# ============================================================

def evaluate_plant_with_model(
    plant: PlantState,
) -> list[MLAnomalyFinding]:
    """
    RUNNING durumundaki tüm HES ünitelerini
    ML modeliyle analiz eder.

    STOPPED üniteler analiz edilmez çünkü
    0 Hz ve 0 rpm gibi değerler dururken normaldir.
    """

    model = get_anomaly_model()

    findings: list[
        MLAnomalyFinding
    ] = []

    for unit in plant.units:

        if (
            unit.status
            != UnitStatus.RUNNING
        ):
            continue

        finding = (
            evaluate_unit_with_model(
                unit=unit,
                model=model,
            )
        )

        findings.append(
            finding
        )

    return findings
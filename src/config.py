"""Proje genelinde kullanilan dosya yollari, sabitler ve risk esigi ayarlari."""
import json
import logging
import math
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
EXPORTS_DIR = BASE_DIR / "exports"

DATA_PATH = DATA_DIR / "bank_customers.csv"
PREDICTIONS_PATH = DATA_DIR / "predictions.csv"
MODEL_PATH = MODELS_DIR / "churn_model.joblib"
METRICS_PATH = MODELS_DIR / "metrics.json"
CONFIG_PATH = BASE_DIR / "config.json"

RANDOM_STATE = 42   # tekrarlanabilir sonuclar icin
TEST_SIZE = 0.20    # verinin %20'si teste ayrilir

# Risk seviyeleri: olasilik < low_max -> Dusuk, low_max <= olasilik < high_min -> Orta,
# olasilik >= high_min -> Yuksek
DEFAULT_RISK_THRESHOLDS = {"low_max": 0.30, "high_min": 0.60}


def validate_risk_thresholds(low_max, high_min) -> dict:
    """Esikleri dogrular (0 < low_max < high_min < 1). Gecersizse ValueError firlatir."""
    try:
        low, high = float(low_max), float(high_min)
    except (TypeError, ValueError):
        raise ValueError("Eşik değerleri sayı olmalıdır.")
    if not (math.isfinite(low) and math.isfinite(high)):
        raise ValueError("Eşik değerleri geçerli bir sayı olmalıdır.")
    if not (0 < low < high < 1):
        raise ValueError("Eşikler şu koşulu sağlamalıdır: 0 < düşük risk sınırı < yüksek risk sınırı < 1.")
    return {"low_max": round(low, 4), "high_min": round(high, 4)}


def load_risk_thresholds(path: Path = CONFIG_PATH) -> dict:
    """config.json'dan risk esiklerini okur. Dosya yoksa/bozuksa varsayilanlari dondurur."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        section = data["risk_thresholds"]
        return validate_risk_thresholds(section["low_max"], section["high_min"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("config.json okunamadi (%s); varsayilan esikler kullaniliyor.", exc)
        return dict(DEFAULT_RISK_THRESHOLDS)


def save_risk_thresholds(low_max, high_min, path: Path = CONFIG_PATH) -> dict:
    """Esikleri dogrulayip config.json'a yazar (yazma sirasinda dosya bozulmasin diye gecici dosya kullanir)."""
    thresholds = validate_risk_thresholds(low_max, high_min)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data["risk_thresholds"] = thresholds

    fd, tmp_name = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
    return thresholds
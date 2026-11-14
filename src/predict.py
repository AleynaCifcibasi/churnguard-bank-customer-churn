"""Kayitli modeli yukler; girdi dogrulama, tekil tahmin, risk seviyesi ve aciklama uretir.

Model burada ASLA egitilmez; yalnizca models/churn_model.joblib okunur.
"""
import logging
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.config import MODEL_PATH
from src.preprocessing import (
    BINARY_FEATURES,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
)

logger = logging.getLogger(__name__)

RISK_LABELS = {"low": "Düşük", "medium": "Orta", "high": "Yüksek"}

FEATURE_LABELS = {
    "Age": "Yaş",
    "CreditScore": "Kredi skoru",
    "Tenure": "Müşteri süresi (yıl)",
    "Balance": "Hesap bakiyesi",
    "EstimatedSalary": "Tahmini maaş",
    "Complaints": "Şikayet sayısı",
    "Gender": "Cinsiyet",
    "Geography": "Bölge",
    "NumOfProducts": "Ürün sayısı",
    "HasCrCard": "Kredi kartı",
    "IsActiveMember": "Aktif üyelik",
}

# Sayisal alan kurallari: (tur, en az, en cok)
NUMERIC_RULES = {
    "Age": ("int", 18, 100),
    "CreditScore": ("number", 300, 850),
    "Tenure": ("int", 0, 40),
    "Balance": ("number", 0, 1_000_000_000),
    "EstimatedSalary": ("number", 0, 1_000_000_000),
    "Complaints": ("int", 0, 20),
    "NumOfProducts": ("int", 1, 4),
}


class ModelNotAvailableError(RuntimeError):
    """Model dosyasi yok veya okunamiyor."""


# ----------------------------------------------------------------- Risk seviyesi
def risk_level(probability: float, thresholds: dict) -> str:
    """Olasiliga gore 'low' / 'medium' / 'high' dondurur."""
    if probability >= thresholds["high_min"]:
        return "high"
    if probability >= thresholds["low_max"]:
        return "medium"
    return "low"


def risk_levels(probabilities, thresholds: dict) -> np.ndarray:
    """risk_level'in toplu (vektorel) surumu."""
    p = np.asarray(probabilities, dtype=float)
    return np.select(
        [p >= thresholds["high_min"], p >= thresholds["low_max"]],
        ["high", "medium"],
        default="low",
    )


# ------------------------------------------------------------- Girdi dogrulama
def _parse_number(value, label, kind, low, high):
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{label} zorunludur.")
    try:
        number = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} sayı olmalıdır.")
    if not math.isfinite(number):
        raise ValueError(f"{label} geçerli bir sayı olmalıdır.")
    if kind == "int":
        if number != int(number):
            raise ValueError(f"{label} tam sayı olmalıdır.")
        number = int(number)
    if not (low <= number <= high):
        raise ValueError(f"{label} {low:,} ile {high:,} arasında olmalıdır.".replace(",", "."))
    return number


def _parse_binary(value, label):
    mapping = {"0": 0, "1": 1, "true": 1, "false": 0, "evet": 1, "hayir": 0, "hayır": 0}
    if isinstance(value, bool):
        return int(value)
    key = str(value).strip().lower() if value is not None else ""
    if key not in mapping:
        raise ValueError(f"{label} için 0 (hayır) veya 1 (evet) girilmelidir.")
    return mapping[key]


def validate_customer_input(payload: dict, allowed_categories: dict):
    """Tahmin formundan gelen veriyi dogrular.

    Donus: (temiz_veri, hatalar). Hata yoksa hatalar bos sozluktur.
    """
    clean, errors = {}, {}
    for field in FEATURE_COLUMNS:
        label = FEATURE_LABELS[field]
        value = payload.get(field)
        try:
            if field in NUMERIC_RULES:
                kind, low, high = NUMERIC_RULES[field]
                clean[field] = _parse_number(value, label, kind, low, high)
            elif field in BINARY_FEATURES:
                clean[field] = _parse_binary(value, label)
            else:  # Gender, Geography
                options = {str(o).lower(): o for o in allowed_categories[field]}
                key = str(value).strip().lower() if value is not None else ""
                if key not in options:
                    raise ValueError(f"{label} şunlardan biri olmalıdır: {', '.join(map(str, options.values()))}.")
                clean[field] = options[key]
        except ValueError as exc:
            errors[field] = str(exc)
    return clean, errors


def build_reference_values(df: pd.DataFrame) -> dict:
    """Aciklama icin 'tipik musteri' degerleri: sayisal -> medyan, digerleri -> en sik deger."""
    reference = {}
    for col in NUMERIC_FEATURES:
        reference[col] = float(df[col].median())
    for col in CATEGORICAL_FEATURES + BINARY_FEATURES:
        value = df[col].mode().iloc[0]
        reference[col] = value.item() if hasattr(value, "item") else value
    return reference


def _native(value):
    """numpy/pandas degerlerini JSON'a uygun Python degerine cevirir (NaN -> None)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
    return value


# ----------------------------------------------------------------------- Model
class ChurnModel:
    """Kayitli model dosyasini bir kez yukler ve tahmin islemlerini sunar."""

    def __init__(self, path: Path = MODEL_PATH):
        path = Path(path)
        if not path.exists():
            raise ModelNotAvailableError(
                "Model dosyası bulunamadı. Önce 'python -m src.train' komutunu çalıştırın."
            )
        try:
            artifact = joblib.load(path)
            self.pipeline = artifact["pipeline"]
            self.feature_columns = list(artifact["feature_columns"])
            self.decision_threshold = float(artifact["threshold"])
            self.model_name = artifact["model_name"]
            self.trained_at = artifact["trained_at"]
            self.test_metrics = artifact.get("test_metrics", {})
            self.feature_importance = artifact.get("feature_importance", {})
        except Exception as exc:  # bozuk dosya, surum uyumsuzlugu vb.
            logger.exception("Model yuklenemedi")
            raise ModelNotAvailableError(
                "Model dosyası okunamadı (bozuk veya farklı bir sürümle kaydedilmiş olabilir). "
                "'python -m src.train' komutuyla modeli yeniden eğitin."
            ) from exc

        encoder = self.pipeline.named_steps["preprocessor"].named_transformers_["cat"].named_steps["encoder"]
        categories = dict(zip(CATEGORICAL_FEATURES, encoder.categories_))
        self.allowed_categories = {
            col: [_native(c) for c in categories[col]] for col in ("Gender", "Geography")
        }
        logger.info("Model yuklendi: %s (%s)", self.model_name, self.trained_at)

    def info(self) -> dict:
        return {
            "model_name": self.model_name,
            "trained_at": self.trained_at,
            "test_metrics": self.test_metrics,
        }

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """Bir tablo icin ayrilma olasiliklarini dondurur."""
        return self.pipeline.predict_proba(df[self.feature_columns])[:, 1]

    def predict_one(self, features: dict) -> float:
        return float(self.predict_proba(pd.DataFrame([features]))[0])

    def explain(self, features: dict, reference: dict, top_n: int = 5) -> list:
        """Her ozelligi 'tipik musteri' degeriyle degistirip olasiligin ne kadar oynadigina bakar.

        Pozitif etki: bu ozellik riski artiriyor. Negatif: azaltiyor.
        Not: Bu bir model katkisi aciklamasidir, nedensellik iddiasi degildir.
        """
        base = pd.DataFrame([features])[self.feature_columns]
        variants = [base]
        for col in self.feature_columns:
            variant = base.copy()
            variant[col] = [reference[col]]
            variants.append(variant)
        probs = self.predict_proba(pd.concat(variants, ignore_index=True))
        impacts = probs[0] - probs[1:]

        factors = []
        for col, impact in zip(self.feature_columns, impacts):
            factors.append({
                "feature": col,
                "label": FEATURE_LABELS[col],
                "value": _native(features.get(col)),
                "typical_value": _native(reference[col]),
                "impact_pct_points": round(float(impact) * 100, 1),
                "direction": "increases" if impact > 0 else "decreases",
            })
        factors.sort(key=lambda f: abs(f["impact_pct_points"]), reverse=True)
        return [f for f in factors if abs(f["impact_pct_points"]) >= 0.1][:top_n]
"""Ortak test yardimcilari (fixture'lar)."""
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.config import CONFIG_PATH, DATA_PATH, MODEL_PATH, PREDICTIONS_PATH


def make_customers(n: int = 300, seed: int = 0, churn_rate: float = 0.2) -> pd.DataFrame:
    """Kucuk, kurgusal ve temiz bir musteri tablosu uretir (testler icin)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "CustomerID": [f"T{i:05d}" for i in range(n)],
        "Age": rng.integers(18, 80, n),
        "Gender": rng.choice(["Female", "Male"], n),
        "Geography": rng.choice(["Marmara", "Ege", "Akdeniz"], n),
        "CreditScore": rng.integers(300, 850, n).astype(float),
        "Tenure": rng.integers(0, 11, n),
        "Balance": rng.uniform(0, 200_000, n).round(2),
        "NumOfProducts": rng.integers(1, 5, n),
        "HasCrCard": rng.integers(0, 2, n),
        "IsActiveMember": rng.integers(0, 2, n),
        "EstimatedSalary": rng.uniform(20_000, 200_000, n).round(2),
        "Complaints": rng.integers(0, 4, n),
        "CustomerSegment": rng.choice(["Standard", "Gold", "Premium"], n),
        "Exited": (rng.random(n) < churn_rate).astype(int),
    })


@pytest.fixture
def customers_df() -> pd.DataFrame:
    return make_customers()


@pytest.fixture(scope="module")
def client():
    """Gercek model ve veriyle Flask test istemcisi. Model/veri yoksa testler atlanir."""
    if not (MODEL_PATH.exists() and PREDICTIONS_PATH.exists() and DATA_PATH.exists()):
        pytest.skip("Model veya veri yok. Once 'python src/generate_data.py' ve 'python -m src.train' calistirin.")
    from app import create_app
    return create_app().test_client()


@pytest.fixture
def restore_config():
    """config.json'u degistiren testlerden sonra eski haline getirir."""
    original = Path(CONFIG_PATH).read_bytes() if Path(CONFIG_PATH).exists() else None
    yield
    if original is None:
        Path(CONFIG_PATH).unlink(missing_ok=True)
    else:
        Path(CONFIG_PATH).write_bytes(original)


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    """CSV raporlari proje klasorune degil gecici klasore yazilsin."""
    monkeypatch.setattr("src.reports.EXPORTS_DIR", tmp_path)
    monkeypatch.setattr("app.EXPORTS_DIR", tmp_path)
    return tmp_path
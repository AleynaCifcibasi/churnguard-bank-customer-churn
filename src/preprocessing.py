"""Veri yukleme, kalite raporu, temizleme ve model oncesi donusumler.

Kural: Eksik deger doldurma, olcekleme ve kodlama temizleme asamasinda DEGIL,
sklearn Pipeline'i icinde yapilir. Boylece bu islemler yalnizca egitim verisine
fit edilir ve test verisinin bilgisi egitime sizmaz (veri sizintisi onlenir).

Test icin (proje kok klasorunden):
    python -m src.preprocessing
"""
import logging
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import DATA_PATH, RANDOM_STATE, TEST_SIZE

logger = logging.getLogger(__name__)

# ------------------------------------------------------------ Sutun tanimlari
ID_COLUMN = "CustomerID"
TARGET_COLUMN = "Exited"

NUMERIC_FEATURES = ["Age", "CreditScore", "Tenure", "Balance", "EstimatedSalary", "Complaints"]
# NumOfProducts sayi gibi gorunur ama etkisi dogrusal degil (2 urun en sadik),
# bu yuzden kategori olarak kodlanir.
CATEGORICAL_FEATURES = ["Gender", "Geography", "NumOfProducts"]
BINARY_FEATURES = ["HasCrCard", "IsActiveMember"]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BINARY_FEATURES

# CustomerSegment modele GIRMEZ: Bakiye ve Maas'tan turetildigi icin yeni bilgi
# icermez. Yalnizca dashboard'da gruplama icin kullanilir.
REQUIRED_COLUMNS = [ID_COLUMN, TARGET_COLUMN, "CustomerSegment"] + FEATURE_COLUMNS


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """CSV dosyasini okur; dosya veya sutun eksikse anlasilir hata verir."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Veri dosyasi bulunamadi: {path}. Once 'python src/generate_data.py' calistirin."
        )
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Veri dosyasinda eksik sutunlar var: {missing}")
    return df


def data_quality_report(df: pd.DataFrame) -> dict:
    """Eksik deger, tekrar kayit ve sinif dengesi hakkinda ozet dondurur."""
    missing = df.isna().sum()
    class_counts = df[TARGET_COLUMN].value_counts().to_dict()
    majority = max(class_counts.values())
    minority = min(class_counts.values())
    return {
        "n_rows": len(df),
        "n_columns": df.shape[1],
        "n_duplicate_rows": int(df.duplicated().sum()),
        "n_duplicate_ids": int(df[ID_COLUMN].duplicated().sum()),
        "missing_values": {c: int(n) for c, n in missing.items() if n > 0},
        "class_counts": {int(k): int(v) for k, v in class_counts.items()},
        "churn_rate": float(df[TARGET_COLUMN].mean()),
        "imbalance_ratio": round(majority / minority, 2),
    }


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Tekrar kayitlari ve hedefi bos satirlari siler.

    Eksik degerler burada DOLDURULMAZ, Pipeline icindeki imputer doldurur.
    """
    before = len(df)
    df = df.drop_duplicates()                              # birebir ayni satirlar
    df = df.drop_duplicates(subset=ID_COLUMN, keep="first")  # ayni ID'li satirlar
    df = df.dropna(subset=[TARGET_COLUMN]).copy()
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(int)
    df = df.reset_index(drop=True)
    logger.info("Temizleme: %d -> %d satir (%d silindi)", before, len(df), before - len(df))
    return df


def build_preprocessor() -> ColumnTransformer:
    """Eksik doldurma + olcekleme + kodlama adimlarini tek nesnede toplar."""
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_FEATURES),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
            ("bin", "passthrough", BINARY_FEATURES),
        ],
        remainder="drop",  # CustomerID, CustomerSegment, Exited modele girmez
    )


def split_data(df: pd.DataFrame):
    """Veriyi sinif oranini koruyarak %80 egitim / %20 test olarak boler."""
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]
    return train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )


def get_feature_names(preprocessor: ColumnTransformer) -> list:
    """Donusumden sonra olusan sutun adlarini dondurur (fit edilmis olmali)."""
    names = preprocessor.get_feature_names_out()
    return [n.split("__", 1)[1] for n in names]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    raw = load_data()
    report = data_quality_report(raw)
    print("--- Ham veri kalite raporu ---")
    for key, value in report.items():
        print(f"{key}: {value}")

    df = clean_data(raw)
    print("\n--- Temizlik sonrasi ---")
    print(f"Satir sayisi: {len(df)}")
    print(f"Tekrar kayit: {df.duplicated().sum()}")

    X_train, X_test, y_train, y_test = split_data(df)
    print(f"\nEgitim: {X_train.shape}, Test: {X_test.shape}")
    print(f"Egitim churn orani: {y_train.mean():.3f} | Test churn orani: {y_test.mean():.3f}")

    preprocessor = build_preprocessor()
    X_train_t = preprocessor.fit_transform(X_train)   # yalnizca egitime fit
    X_test_t = preprocessor.transform(X_test)         # teste sadece uygula
    print(f"\nDonusum sonrasi egitim: {X_train_t.shape}, test: {X_test_t.shape}")
    print(f"Egitimde kalan NaN: {int(pd.isna(X_train_t).sum())}")
    print("Ozellikler:", get_feature_names(preprocessor))


if __name__ == "__main__":
    main()
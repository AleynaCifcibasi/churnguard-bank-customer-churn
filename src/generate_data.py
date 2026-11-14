"""Sentetik banka musteri verisi uretir (tamamen kurgusal).

Calistirma (proje kok klasorunden):
    python src/generate_data.py

Cikti: data/bank_customers.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- Ayarlar
SEED = 42
N_ROWS = 10_000          # toplam satir (tekrar kayitlar dahil)
N_DUPLICATES = 25        # bilincli eklenen tekrar kayit sayisi
TARGET_CHURN_RATE = 0.20  # hedef genel ayrilma orani
MISSING_RATE = 0.015     # secili sutunlarda eksik deger orani
MISSING_COLUMNS = ["CreditScore", "EstimatedSalary", "Geography"]

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "bank_customers.csv"

GEOGRAPHIES = [
    "Marmara", "Ege", "Akdeniz", "Ic Anadolu",
    "Karadeniz", "Dogu Anadolu", "Guneydogu Anadolu",
]
GEOGRAPHY_PROBS = [0.30, 0.15, 0.13, 0.17, 0.09, 0.07, 0.09]

# Bolgelere gore ayrilma egilimi (logit'e eklenen kucuk etki)
GEOGRAPHY_EFFECT = {
    "Marmara": 0.00, "Ege": 0.05, "Akdeniz": 0.10, "Ic Anadolu": -0.05,
    "Karadeniz": -0.10, "Dogu Anadolu": 0.20, "Guneydogu Anadolu": 0.15,
}
# Urun sayisinin ayrilmaya etkisi (2 urun en sadik, 3-4 urun riskli)
PRODUCT_EFFECT = {1: 0.30, 2: -0.80, 3: 1.20, 4: 2.50}


def assign_segment(balance: pd.Series, salary: pd.Series) -> pd.Series:
    """Musteri segmentini kurallara gore turetir.

    Premium : Bakiye >= 150.000 veya Maas >= 170.000
    Gold    : Bakiye >= 80.000  veya Maas >= 110.000
    Standart: diger tum musteriler
    """
    conditions = [
        (balance >= 150_000) | (salary >= 170_000),
        (balance >= 80_000) | (salary >= 110_000),
    ]
    return pd.Series(
        np.select(conditions, ["Premium", "Gold"], default="Standard"),
        index=balance.index,
    )


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _calibrate_intercept(base_logit: np.ndarray, target: float) -> float:
    """Ortalama ayrilma olasiligi hedefe esit olacak sekilde kesim noktasini bulur."""
    low, high = -15.0, 15.0
    for _ in range(60):
        mid = (low + high) / 2
        if _sigmoid(base_logit + mid).mean() < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def generate_customers(n_unique: int, rng: np.random.Generator) -> pd.DataFrame:
    """Temiz (eksiksiz, tekrarsiz) musteri tablosunu ve hedef degiskeni uretir."""
    age = np.clip(rng.normal(40, 11, n_unique), 18, 85).round().astype(int)
    gender = rng.choice(["Female", "Male"], size=n_unique, p=[0.48, 0.52])
    geography = rng.choice(GEOGRAPHIES, size=n_unique, p=GEOGRAPHY_PROBS)
    credit_score = np.clip(rng.normal(650, 90, n_unique), 300, 850).round().astype(int)
    tenure = rng.integers(0, 11, size=n_unique)

    has_balance = rng.random(n_unique) > 0.25  # musterilerin ~%25'inin bakiyesi 0
    balance = np.where(
        has_balance,
        np.clip(rng.normal(100_000, 40_000, n_unique), 1_000, None),
        0.0,
    ).round(2)

    products = rng.choice([1, 2, 3, 4], size=n_unique, p=[0.46, 0.45, 0.07, 0.02])
    has_cr_card = (rng.random(n_unique) < 0.70).astype(int)
    is_active = (rng.random(n_unique) < 0.52).astype(int)
    salary = rng.uniform(20_000, 200_000, n_unique).round(2)

    # Pasif musterilerde sikayet daha sik gorulur
    complaint_rate = np.where(is_active == 1, 0.25, 0.60)
    complaints = np.clip(rng.poisson(complaint_rate), 0, 5)

    # Ayrilma olasiligi: lojistik fonksiyon + gurultu
    logit = (
        0.045 * (age - 40)
        + 0.70 * (age >= 50)
        + np.array([PRODUCT_EFFECT[p] for p in products])
        - 1.00 * is_active
        + 0.55 * complaints
        - 0.004 * (credit_score - 650)
        + 0.40 * (balance > 120_000)
        - 0.04 * tenure
        + 0.25 * (gender == "Female")
        - 0.10 * has_cr_card
        + np.array([GEOGRAPHY_EFFECT[g] for g in geography])
        + rng.normal(0, 0.5, n_unique)
    )
    logit = logit + _calibrate_intercept(logit, TARGET_CHURN_RATE)
    exited = (rng.random(n_unique) < _sigmoid(logit)).astype(int)

    df = pd.DataFrame({
        "CustomerID": [f"C{100001 + i}" for i in range(n_unique)],
        "Age": age,
        "Gender": gender,
        "Geography": geography,
        "CreditScore": credit_score.astype(float),
        "Tenure": tenure,
        "Balance": balance,
        "NumOfProducts": products,
        "HasCrCard": has_cr_card,
        "IsActiveMember": is_active,
        "EstimatedSalary": salary,
        "Complaints": complaints,
    })
    df["CustomerSegment"] = assign_segment(df["Balance"], df["EstimatedSalary"])
    df["Exited"] = exited
    return df


def inject_data_quality_issues(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """On isleme adimlarini gostermek icin eksik deger ve tekrar kayit ekler."""
    df = df.copy()
    for col in MISSING_COLUMNS:
        mask = rng.random(len(df)) < MISSING_RATE
        df[col] = df[col].astype(object).where(~mask, np.nan) if col == "Geography" \
            else df[col].mask(mask)

    duplicates = df.sample(n=N_DUPLICATES, random_state=SEED)
    df = pd.concat([df, duplicates], ignore_index=True)
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


def main() -> None:
    rng = np.random.default_rng(SEED)
    clean = generate_customers(N_ROWS - N_DUPLICATES, rng)
    final = inject_data_quality_issues(clean, rng)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"Dosya yazildi: {OUTPUT_PATH}")
    print(f"Satir x sutun : {final.shape[0]} x {final.shape[1]}")
    print(f"Churn orani   : {final['Exited'].mean():.1%}")
    print(f"Tekrar kayit  : {final.duplicated().sum()}")
    print("Eksik degerler:")
    print(final.isna().sum()[final.isna().sum() > 0].to_string())
    print("Segment dagilimi:")
    print(final["CustomerSegment"].value_counts(normalize=True).round(3).to_string())


if __name__ == "__main__":
    main()
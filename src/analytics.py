"""Dashboard ve musteri listesi icin veri hazirlama (okuma amacli, model egitmez).

Musteri tablosu ile data/predictions.csv birlestirilir; risk seviyeleri her
istekte guncel esiklerle hesaplanir, bu yuzden esik degisince model yeniden egitilmez.
"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DATA_PATH, PREDICTIONS_PATH
from src.predict import RISK_LABELS, risk_levels
from src.preprocessing import FEATURE_COLUMNS, ID_COLUMN, TARGET_COLUMN, clean_data, load_data

logger = logging.getLogger(__name__)

PROB_COLUMN = "ChurnProbability"
AGE_BINS = [17, 30, 40, 50, 60, 120]
AGE_LABELS = ["18-30", "31-40", "41-50", "51-60", "60+"]
SEGMENT_ORDER = ["Standard", "Gold", "Premium"]
RISK_ORDER = ["low", "medium", "high"]

# Siralama icin izin verilen sutunlar (API adi -> tablo sutunu)
SORT_COLUMNS = {
    "customer_id": ID_COLUMN,
    "age": "Age",
    "credit_score": "CreditScore",
    "balance": "Balance",
    "num_products": "NumOfProducts",
    "churn_probability": PROB_COLUMN,
}


class DataNotAvailableError(RuntimeError):
    """Veri veya tahmin dosyasi yok / uyumsuz."""


def _none_if_nan(value):
    return None if pd.isna(value) else (value.item() if hasattr(value, "item") else value)


class CustomerStore:
    """Temizlenmis musteri verisini ve model tahminlerini bellekte tutar."""

    def __init__(self, data_path: Path = DATA_PATH, predictions_path: Path = PREDICTIONS_PATH):
        try:
            df = clean_data(load_data(data_path))
        except (FileNotFoundError, ValueError) as exc:
            raise DataNotAvailableError(
                f"{exc} Önce 'python src/generate_data.py' ve 'python -m src.train' komutlarını çalıştırın."
            ) from exc

        if not Path(predictions_path).exists():
            raise DataNotAvailableError(
                "Tahmin dosyası (data/predictions.csv) bulunamadı. Önce 'python -m src.train' komutunu çalıştırın."
            )
        preds = pd.read_csv(predictions_path)
        merged = df.merge(preds[[ID_COLUMN, PROB_COLUMN]], on=ID_COLUMN, how="left")
        if merged[PROB_COLUMN].isna().any():
            raise DataNotAvailableError(
                "Tahmin dosyası müşteri verisiyle uyumsuz. 'python -m src.train' komutuyla yeniden üretin."
            )
        merged["AgeGroup"] = pd.cut(merged["Age"], bins=AGE_BINS, labels=AGE_LABELS).astype(str)
        self.df = merged
        logger.info("Musteri verisi yuklendi: %d kayit", len(merged))

    # ------------------------------------------------------------ yardimcilar
    def _with_risk(self, thresholds: dict) -> pd.DataFrame:
        df = self.df.copy()
        df["RiskLevel"] = risk_levels(df[PROB_COLUMN], thresholds)
        return df

    @staticmethod
    def _risk_counts(df: pd.DataFrame) -> dict:
        counts = df["RiskLevel"].value_counts()
        return {level: int(counts.get(level, 0)) for level in RISK_ORDER}

    @staticmethod
    def _churn_by(df, column, order=None, label_map=None) -> dict:
        grouped = df.groupby(column, dropna=False)[TARGET_COLUMN].agg(["mean", "sum", "count"])
        if order is not None:
            grouped = grouped.reindex([o for o in order if o in grouped.index])
        labels = [label_map.get(i, str(i)) if label_map else str(i) for i in grouped.index]
        return {
            "labels": labels,
            "churn_rate_pct": [round(float(v) * 100, 1) for v in grouped["mean"]],
            "churned": [int(v) for v in grouped["sum"]],
            "total": [int(v) for v in grouped["count"]],
        }

    @staticmethod
    def _row_to_item(row) -> dict:
        probability = float(row[PROB_COLUMN])
        return {
            "customer_id": row[ID_COLUMN],
            "age": int(row["Age"]),
            "gender": row["Gender"],
            "credit_score": _none_if_nan(row["CreditScore"]),
            "balance": float(row["Balance"]),
            "num_products": int(row["NumOfProducts"]),
            "is_active_member": int(row["IsActiveMember"]),
            "churn_probability": round(probability, 4),
            "churn_probability_pct": round(probability * 100, 1),
            "risk_level": row["RiskLevel"],
            "risk_label": RISK_LABELS[row["RiskLevel"]],
            "exited": int(row[TARGET_COLUMN]),
        }

    # ------------------------------------------------------------- dashboard
    def summary(self, thresholds: dict) -> dict:
        """Dashboard kartlari. 'Aktif musteri' = bankada kalan (Exited=0) musteri."""
        df = self._with_risk(thresholds)
        total = len(df)
        churned = int(df[TARGET_COLUMN].sum())
        active_df = df[df[TARGET_COLUMN] == 0]
        return {
            "total_customers": total,
            "churned_customers": churned,
            "active_customers": total - churned,
            "churn_rate_pct": round(churned / total * 100, 1),
            "risk_counts_active": self._risk_counts(active_df),
            "risk_counts_all": self._risk_counts(df),
            "thresholds": thresholds,
        }

    def charts(self, thresholds: dict) -> dict:
        """Dashboard grafikleri icin veri."""
        df = self._with_risk(thresholds)
        churned = int(df[TARGET_COLUMN].sum())
        active_df = df[df[TARGET_COLUMN] == 0]

        by_outcome = {
            "stayed": [int(((df["RiskLevel"] == lvl) & (df[TARGET_COLUMN] == 0)).sum()) for lvl in RISK_ORDER],
            "churned": [int(((df["RiskLevel"] == lvl) & (df[TARGET_COLUMN] == 1)).sum()) for lvl in RISK_ORDER],
        }
        risk_labels = [RISK_LABELS[lvl] for lvl in RISK_ORDER]

        return {
            "churn_distribution": {"labels": ["Kaldı", "Ayrıldı"], "values": [len(df) - churned, churned]},
            "risk_distribution_active": {
                "labels": risk_labels,
                "values": [self._risk_counts(active_df)[lvl] for lvl in RISK_ORDER],
            },
            "risk_by_outcome": {"labels": risk_labels, **by_outcome},
            "churn_by_age": self._churn_by(df, "AgeGroup", order=AGE_LABELS),
            "churn_by_gender": self._churn_by(df, "Gender", label_map={"Female": "Kadın", "Male": "Erkek"}),
            "churn_by_credit_card": self._churn_by(
                df, "HasCrCard", label_map={0: "Kredi kartı yok", 1: "Kredi kartı var"}
            ),
            "churn_by_segment": self._churn_by(df, "CustomerSegment", order=SEGMENT_ORDER),
            "churn_by_geography": self._churn_by(df.assign(Geography=df["Geography"].fillna("Bilinmiyor")), "Geography"),
        }

    def notifications(self, thresholds: dict) -> list:
        """Gercek veriden uretilen bildirimler."""
        df = self._with_risk(thresholds)
        active = df[df[TARGET_COLUMN] == 0]
        high = int((active["RiskLevel"] == "high").sum())
        notes = []
        if high:
            share = high / len(active) * 100
            notes.append({
                "level": "danger",
                "message": (
                    f"{high:,}".replace(",", ".")
                    + f" aktif müşteri yüksek risk grubunda (aktif müşterilerin %{share:.1f}".replace(".", ",")
                    + "'i)."
                ),
            })
        inactive_high = int(((active["RiskLevel"] == "high") & (active["IsActiveMember"] == 0)).sum())
        if inactive_high:
            notes.append({
                "level": "warning",
                "message": "Yüksek riskli müşterilerin " + f"{inactive_high:,}".replace(",", ".") + " tanesi pasif üye.",
            })
        return notes

    # --------------------------------------------------------- musteri listesi
    def list_customers(self, thresholds, page=1, per_page=25, search=None, risk=None,
                       gender=None, segment=None, active_member=None, status=None,
                       sort_by="customer_id", sort_order="asc") -> dict:
        df = self._with_risk(thresholds)

        if search:
            df = df[df[ID_COLUMN].str.contains(search, case=False, regex=False)]
        if risk:
            df = df[df["RiskLevel"] == risk]
        if gender:
            df = df[df["Gender"] == gender]
        if segment:
            df = df[df["CustomerSegment"] == segment]
        if active_member is not None:
            df = df[df["IsActiveMember"] == active_member]
        if status == "churned":
            df = df[df[TARGET_COLUMN] == 1]
        elif status == "active":
            df = df[df[TARGET_COLUMN] == 0]

        df = df.sort_values(SORT_COLUMNS[sort_by], ascending=(sort_order == "asc"), kind="stable")

        total = len(df)
        total_pages = max(1, int(np.ceil(total / per_page)))
        page = min(page, total_pages)
        chunk = df.iloc[(page - 1) * per_page: page * per_page]
        return {
            "items": [self._row_to_item(row) for _, row in chunk.iterrows()],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        }

    def get_customer(self, customer_id: str, thresholds: dict):
        """Tek musterinin tum bilgilerini dondurur; yoksa None."""
        df = self._with_risk(thresholds)
        match = df[df[ID_COLUMN] == customer_id]
        if match.empty:
            return None
        row = match.iloc[0]
        item = self._row_to_item(row)
        item.update({
            "geography": _none_if_nan(row["Geography"]),
            "tenure": int(row["Tenure"]),
            "estimated_salary": _none_if_nan(row["EstimatedSalary"]),
            "complaints": int(row["Complaints"]),
            "has_credit_card": int(row["HasCrCard"]),
            "segment": row["CustomerSegment"],
        })
        return item

    def get_feature_row(self, customer_id: str):
        """Aciklama icin modelin kullandigi ozellikleri dondurur."""
        match = self.df[self.df[ID_COLUMN] == customer_id]
        if match.empty:
            return None
        return {c: _none_if_nan(match.iloc[0][c]) for c in FEATURE_COLUMNS}
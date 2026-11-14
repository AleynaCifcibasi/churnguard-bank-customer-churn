"""Raporlama: CSV dosyalari uretir ve exports/ klasorune yazar.

Dosyalar zaman damgali adla kaydedilir, tarayici uzerinden indirilebilir.
Excel (Turkce) icin ';' ayraci ve ondalik virgul, standart icin ',' ve ondalik nokta kullanilir.
"""
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.analytics import PROB_COLUMN, CustomerStore
from src.config import EXPORTS_DIR
from src.predict import RISK_LABELS, risk_levels
from src.preprocessing import ID_COLUMN, TARGET_COLUMN

logger = logging.getLogger(__name__)

EXPORT_KINDS = {
    "predictions": {"prefix": "tum_tahminler", "label": "Tüm tahminler"},
    "high_risk": {"prefix": "yuksek_riskli", "label": "Yüksek riskli müşteriler"},
    "summary": {"prefix": "kayip_ozeti", "label": "Kayıp özet raporu"},
}
CSV_FORMATS = {
    "excel": {"sep": ";", "decimal": ","},      # Turkce Excel'de cift tiklayinca duzgun acilir
    "standard": {"sep": ",", "decimal": "."},   # diger araclar icin
}
FILENAME_PATTERN = re.compile(r"^(tum_tahminler|yuksek_riskli|kayip_ozeti)_\d{8}_\d{6}(_\d+)?\.csv$")
_PREFIX_TO_LABEL = {v["prefix"]: v["label"] for v in EXPORT_KINDS.values()}

# Veride bolge adlari ASCII tutuluyor; raporlarda Turkce karakterli gosterilir
GEOGRAPHY_TR = {"Ic Anadolu": "İç Anadolu", "Dogu Anadolu": "Doğu Anadolu", "Guneydogu Anadolu": "Güneydoğu Anadolu"}


def prediction_frame(store: CustomerStore, thresholds: dict, only_high_risk: bool = False) -> pd.DataFrame:
    """Musteri bazli tahmin tablosu (Turkce basliklarla). only_high_risk: bankada kalan yuksek riskliler."""
    df = store.df.copy()
    df["RiskLevel"] = risk_levels(df[PROB_COLUMN], thresholds)
    if only_high_risk:
        df = df[(df["RiskLevel"] == "high") & (df[TARGET_COLUMN] == 0)]
        df = df.sort_values(PROB_COLUMN, ascending=False)
    else:
        df = df.sort_values(ID_COLUMN)

    return pd.DataFrame({
        "Müşteri ID": df[ID_COLUMN],
        "Yaş": df["Age"],
        "Cinsiyet": df["Gender"].map({"Female": "Kadın", "Male": "Erkek"}),
        "Bölge": df["Geography"].fillna("Bilinmiyor").replace(GEOGRAPHY_TR),
        "Kredi Skoru": df["CreditScore"].round().astype("Int64"),
        "Müşteri Süresi (Yıl)": df["Tenure"],
        "Bakiye": df["Balance"].round(2),
        "Ürün Sayısı": df["NumOfProducts"],
        "Kredi Kartı": df["HasCrCard"].map({1: "Var", 0: "Yok"}),
        "Aktif Üyelik": df["IsActiveMember"].map({1: "Aktif", 0: "Pasif"}),
        "Tahmini Maaş": df["EstimatedSalary"].round(2),
        "Şikayet Sayısı": df["Complaints"],
        "Segment": df["CustomerSegment"],
        "Durum": df[TARGET_COLUMN].map({1: "Ayrıldı", 0: "Müşteri"}),
        "Kayıp Olasılığı (%)": (df[PROB_COLUMN] * 100).round(1),
        "Risk Seviyesi": df["RiskLevel"].map(RISK_LABELS),
    })


def summary_frame(store: CustomerStore, thresholds: dict) -> pd.DataFrame:
    """Segment, yas grubu, bolge, cinsiyet ve kredi karti kirilimlarinda kayip ozeti."""
    charts = store.charts(thresholds)
    dimensions = [
        ("Segment", "churn_by_segment"),
        ("Yaş Grubu", "churn_by_age"),
        ("Bölge", "churn_by_geography"),
        ("Cinsiyet", "churn_by_gender"),
        ("Kredi Kartı", "churn_by_credit_card"),
    ]
    rows = []
    for title, key in dimensions:
        block = charts[key]
        for i, label in enumerate(block["labels"]):
            label = GEOGRAPHY_TR.get(label, label) if title == "Bölge" else label
            rows.append({
                "Boyut": title,
                "Grup": label,
                "Toplam Müşteri": block["total"][i],
                "Ayrılan Müşteri": block["churned"][i],
                "Kayıp Oranı (%)": block["churn_rate_pct"][i],
            })
    return pd.DataFrame(rows)


def _unique_path(prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = EXPORTS_DIR / f"{prefix}_{stamp}.csv"
    counter = 2
    while path.exists():
        path = EXPORTS_DIR / f"{prefix}_{stamp}_{counter}.csv"
        counter += 1
    return path


def create_export(store: CustomerStore, thresholds: dict, kind: str, csv_format: str = "excel") -> dict:
    """Istenen raporu CSV olarak exports/ klasorune yazar ve dosya bilgisini dondurur."""
    if kind not in EXPORT_KINDS:
        raise ValueError("Geçersiz rapor türü. Seçenekler: " + ", ".join(EXPORT_KINDS))
    if csv_format not in CSV_FORMATS:
        raise ValueError("Geçersiz CSV biçimi. Seçenekler: " + ", ".join(CSV_FORMATS))

    if kind == "predictions":
        frame = prediction_frame(store, thresholds)
    elif kind == "high_risk":
        frame = prediction_frame(store, thresholds, only_high_risk=True)
    else:
        frame = summary_frame(store, thresholds)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _unique_path(EXPORT_KINDS[kind]["prefix"])
    options = CSV_FORMATS[csv_format]
    tmp_path = path.with_suffix(".tmp")
    # utf-8-sig: Excel Turkce karakterleri dogru okusun. Once gecici dosyaya yazilir, yarim dosya gorunmez.
    frame.to_csv(tmp_path, index=False, sep=options["sep"], decimal=options["decimal"], encoding="utf-8-sig")
    os.replace(tmp_path, path)
    logger.info("Rapor olusturuldu: %s (%d satir)", path.name, len(frame))

    return {
        "filename": path.name,
        "download_url": f"/exports/{path.name}",
        "kind": kind,
        "label": EXPORT_KINDS[kind]["label"],
        "format": csv_format,
        "rows": int(len(frame)),
        "size_kb": round(path.stat().st_size / 1024, 1),
    }


def list_exports(limit: int = 20) -> list:
    """exports/ klasorundeki raporlari, en yeniden eskiye dogru listeler."""
    if not EXPORTS_DIR.exists():
        return []
    files = [p for p in EXPORTS_DIR.glob("*.csv") if FILENAME_PATTERN.match(p.name)]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:limit]:
        info = path.stat()
        label = next((lbl for pre, lbl in _PREFIX_TO_LABEL.items() if path.name.startswith(pre)), "Rapor")
        result.append({
            "filename": path.name,
            "label": label,
            "size_kb": round(info.st_size / 1024, 1),
            "created": datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
            "download_url": f"/exports/{path.name}",
        })
    return result


def resolve_export(filename: str):
    """Indirilebilir dosyanin yolunu dondurur; gecersiz ad veya olmayan dosya icin None."""
    if not FILENAME_PATTERN.match(filename):
        return None
    path = EXPORTS_DIR / filename
    return path if path.is_file() else None
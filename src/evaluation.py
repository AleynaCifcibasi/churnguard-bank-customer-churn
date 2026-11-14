"""Model degerlendirme: metrikler, karar esigi optimizasyonu ve model secimi."""
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

# Secim kurali: once Recall >= MIN_RECALL saglayanlar, aralarindan en yuksek F1
MIN_RECALL = 0.70


def compute_metrics(y_true, y_proba, threshold: float = 0.5) -> dict:
    """Olasiliklari verilen esige gore 0/1'e cevirip tum metrikleri hesaplar."""
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(y_proba) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred)), 4),
        "f1": round(float(f1_score(y_true, y_pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_proba)), 4),
        # [[TN, FP], [FN, TP]]
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def roc_points(y_true, y_proba, n_points: int = 60) -> dict:
    """ROC egrisini grafik cizmek icin seyreltilmis noktalar olarak dondurur."""
    fpr, tpr, _ = roc_curve(y_true, y_proba)
    idx = np.linspace(0, len(fpr) - 1, min(n_points, len(fpr))).astype(int)
    return {"fpr": np.round(fpr[idx], 4).tolist(), "tpr": np.round(tpr[idx], 4).tolist()}


def find_optimal_threshold(y_true, y_proba, min_recall: float = MIN_RECALL):
    """Precision-Recall egrisi uzerinden karar esigini secer.

    Kural: Recall >= min_recall olan esikler arasinda F1'i en yuksek olani sec.
    Hicbir esik bu kosulu saglamazsa, genel olarak F1'i en yuksek esigi sec.

    Not: y_proba, modelin gormedigi veriden (cross-validation tahmini) gelmelidir.
    """
    precision, recall, thresholds = precision_recall_curve(y_true, y_proba)
    precision, recall = precision[:-1], recall[:-1]   # son nokta esiksiz, atilir
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)

    allowed = recall >= min_recall
    constraint_met = bool(allowed.any())
    candidates = np.where(allowed, f1, -1.0) if constraint_met else f1
    best = int(np.argmax(candidates))

    idx = np.linspace(0, len(thresholds) - 1, min(100, len(thresholds))).astype(int)
    curve = {
        "thresholds": np.round(thresholds[idx], 4).tolist(),
        "precision": np.round(precision[idx], 4).tolist(),
        "recall": np.round(recall[idx], 4).tolist(),
        "f1": np.round(f1[idx], 4).tolist(),
    }
    info = {"constraint_met": constraint_met, "min_recall": min_recall, "curve": curve}
    return float(thresholds[best]), info


def select_best_model(results: dict, min_recall: float = MIN_RECALL):
    """Secim kurali: Recall >= min_recall olanlar arasinda en yuksek F1 (esitlikte ROC-AUC).

    Hicbiri kosulu saglamazsa en yuksek F1'li model secilir.
    Donus: (model_adi, aciklama_metni)
    """
    scores = {name: r["test_metrics"] for name, r in results.items()}
    eligible = {n: m for n, m in scores.items() if m["recall"] >= min_recall}
    if eligible:
        pool, reason = eligible, f"Recall >= {min_recall:.2f} kosulunu saglayan modeller arasinda en yuksek F1"
    else:
        pool, reason = scores, f"Hicbir model Recall >= {min_recall:.2f} saglamadi; en yuksek F1 secildi"
    best = max(pool, key=lambda n: (pool[n]["f1"], pool[n]["roc_auc"]))
    return best, reason
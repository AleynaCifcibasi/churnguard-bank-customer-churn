"""Modelleri egitir, karsilastirir, en iyisini secip kaydeder.

Calistirma (proje kok klasorunden):
    python -m src.train

Uretilen dosyalar:
    models/churn_model.joblib  -> secilen model + karar esigi + meta bilgi
    models/metrics.json        -> karsilastirma sonuclari
    data/predictions.csv       -> tum musteriler icin out-of-fold risk olasiliklari
"""
import json
import logging
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    ParameterGrid,
    RandomizedSearchCV,
    StratifiedKFold,
    cross_val_predict,
)
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils.class_weight import compute_sample_weight

from src.config import METRICS_PATH, MODEL_PATH, MODELS_DIR, PREDICTIONS_PATH, RANDOM_STATE
from src.evaluation import (
    MIN_RECALL,
    compute_metrics,
    find_optimal_threshold,
    roc_points,
    select_best_model,
)
from src.preprocessing import (
    FEATURE_COLUMNS,
    ID_COLUMN,
    TARGET_COLUMN,
    build_preprocessor,
    clean_data,
    data_quality_report,
    get_feature_names,
    load_data,
    split_data,
)

logger = logging.getLogger(__name__)

CV_FOLDS = 5
N_SEARCH_ITER = 12   # her model icin denenecek rastgele parametre kombinasyonu


def get_model_configs() -> dict:
    """Dort modeli ve hiperparametre arama uzaylarini dondurur.

    use_sample_weight=True: model class_weight desteklemiyor, dengesizlik
    ornek agirliklariyla (sample_weight) ele alinir.
    """
    return {
        "Logistic Regression": {
            "estimator": LogisticRegression(
                class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE
            ),
            "params": {"classifier__C": [0.01, 0.1, 1, 10, 100]},
            "use_sample_weight": False,
        },
        "Decision Tree": {
            "estimator": DecisionTreeClassifier(
                class_weight="balanced", random_state=RANDOM_STATE
            ),
            "params": {
                "classifier__max_depth": [3, 4, 5, 6, 8, 10],
                "classifier__min_samples_leaf": [5, 10, 20, 50],
            },
            "use_sample_weight": False,
        },
        "Random Forest": {
            "estimator": RandomForestClassifier(
                class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1
            ),
            "params": {
                "classifier__n_estimators": [100, 200, 300],
                "classifier__max_depth": [6, 8, 12, None],
                "classifier__min_samples_leaf": [1, 3, 5, 10],
            },
            "use_sample_weight": False,
        },
        "Gradient Boosting": {
            "estimator": GradientBoostingClassifier(random_state=RANDOM_STATE),
            "params": {
                "classifier__n_estimators": [100, 200, 300],
                "classifier__learning_rate": [0.03, 0.05, 0.1],
                "classifier__max_depth": [2, 3, 4],
                "classifier__subsample": [0.7, 0.85, 1.0],
            },
            "use_sample_weight": True,
        },
    }


def _fit_params(use_sample_weight: bool, y) -> dict:
    """Gerekirse dengeleme icin ornek agirliklarini hazirlar."""
    if not use_sample_weight:
        return {}
    return {"classifier__sample_weight": compute_sample_weight("balanced", y)}


def extract_feature_importance(pipeline: Pipeline) -> dict:
    """Modelin hangi ozellikleri ne kadar onemsedigini (buyukten kucuge) dondurur."""
    names = get_feature_names(pipeline.named_steps["preprocessor"])
    model = pipeline.named_steps["classifier"]
    if hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:                                   # Logistic Regression: katsayinin mutlak degeri
        values = np.abs(model.coef_[0])
    values = values / values.sum()
    ranked = sorted(zip(names, values), key=lambda x: x[1], reverse=True)
    return {name: round(float(v), 4) for name, v in ranked}


def train_and_compare(X_train, X_test, y_train, y_test) -> dict:
    """Her modeli parametre aramasiyla egitir ve test verisinde degerlendirir."""
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    results = {}

    for name, cfg in get_model_configs().items():
        started = time.time()
        pipeline = Pipeline([
            ("preprocessor", build_preprocessor()),
            ("classifier", cfg["estimator"]),
        ])
        n_iter = min(N_SEARCH_ITER, len(ParameterGrid(cfg["params"])))
        search = RandomizedSearchCV(
            pipeline, cfg["params"], n_iter=n_iter, scoring="f1",
            cv=cv, random_state=RANDOM_STATE, n_jobs=-1,
        )
        search.fit(X_train, y_train, **_fit_params(cfg["use_sample_weight"], y_train))

        best = search.best_estimator_
        y_proba = best.predict_proba(X_test)[:, 1]
        metrics = compute_metrics(y_test, y_proba, threshold=0.5)

        results[name] = {
            "best_params": {k.replace("classifier__", ""): v for k, v in search.best_params_.items()},
            "cv_f1": round(float(search.best_score_), 4),
            "test_metrics": metrics,
            "roc_curve": roc_points(y_test, y_proba),
            "_search": search,            # kaydedilmez, sadece secimden sonra kullanilir
            "_use_sample_weight": cfg["use_sample_weight"],
        }
        logger.info("%-20s CV-F1=%.3f | Test Recall=%.3f F1=%.3f AUC=%.3f (%.0f sn)",
                    name, search.best_score_, metrics["recall"], metrics["f1"],
                    metrics["roc_auc"], time.time() - started)
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Veri
    raw = load_data()
    quality = data_quality_report(raw)
    df = clean_data(raw)
    X_train, X_test, y_train, y_test = split_data(df)
    logger.info("Egitim: %d, Test: %d, Churn orani: %.1f%%",
                len(X_train), len(X_test), df[TARGET_COLUMN].mean() * 100)

    # 2) Dort modeli egit ve karsilastir (esik 0.5)
    results = train_and_compare(X_train, X_test, y_train, y_test)

    # 3) En iyi modeli sec
    best_name, reason = select_best_model(results)
    best_search = results[best_name]["_search"]
    use_sw = results[best_name]["_use_sample_weight"]
    logger.info("SECILEN MODEL: %s (%s)", best_name, reason)

    # 4) Karar esigini egitim verisi uzerindeki out-of-fold tahminlerle belirle
    #    (test verisi kullanilmaz, boylece sizinti olmaz)
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    oof_train = cross_val_predict(
        clone(best_search.best_estimator_), X_train, y_train, cv=cv,
        method="predict_proba", params=_fit_params(use_sw, y_train),
    )[:, 1]
    threshold, threshold_info = find_optimal_threshold(y_train, oof_train)
    logger.info("Optimum karar esigi: %.3f (Recall kosulu saglandi mi: %s)",
                threshold, threshold_info["constraint_met"])

    # 5) Secilen modelin (egitim verisiyle egitilmis) test sonucu, yeni esikle
    test_proba = best_search.best_estimator_.predict_proba(X_test)[:, 1]
    final_test_metrics = compute_metrics(y_test, test_proba, threshold=threshold)
    logger.info("Esik sonrasi TEST: Recall=%.3f Precision=%.3f F1=%.3f",
                final_test_metrics["recall"], final_test_metrics["precision"],
                final_test_metrics["f1"])

    # 6) Nihai model: ayni ayarlarla tum veriyle yeniden egitilir
    X_all, y_all = df[FEATURE_COLUMNS], df[TARGET_COLUMN]
    final_pipeline = clone(best_search.best_estimator_)
    final_pipeline.fit(X_all, y_all, **_fit_params(use_sw, y_all))
    importance = extract_feature_importance(final_pipeline)

    # 7) Dashboard icin tum musterilere out-of-fold olasiliklar
    oof_all = cross_val_predict(
        clone(best_search.best_estimator_), X_all, y_all, cv=cv,
        method="predict_proba", params=_fit_params(use_sw, y_all),
    )[:, 1]
    predictions = pd.DataFrame({
        ID_COLUMN: df[ID_COLUMN],
        "ChurnProbability": np.round(oof_all, 4),
        "PredictedChurn": (oof_all >= threshold).astype(int),
    })
    predictions.to_csv(PREDICTIONS_PATH, index=False)

    # 8) Kaydet
    trained_at = datetime.now().isoformat(timespec="seconds")
    artifact = {
        "pipeline": final_pipeline,
        "threshold": threshold,
        "feature_columns": FEATURE_COLUMNS,
        "model_name": best_name,
        "trained_at": trained_at,
        "sklearn_version": sklearn.__version__,
        "test_metrics": final_test_metrics,
        "feature_importance": importance,
    }
    joblib.dump(artifact, MODEL_PATH)

    metrics_out = {
        "trained_at": trained_at,
        "selected_model": best_name,
        "selection_rule": reason,
        "threshold": round(threshold, 4),
        "data_quality": quality,
        "models": {
            n: {k: v for k, v in r.items() if not k.startswith("_")} for n, r in results.items()
        },
        "selected_model_test_metrics_at_threshold": final_test_metrics,
        "threshold_analysis": threshold_info,
        "feature_importance": importance,
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_out, f, ensure_ascii=False, indent=2)

    logger.info("Kaydedildi: %s, %s, %s", MODEL_PATH.name, METRICS_PATH.name, PREDICTIONS_PATH.name)
    print("\n=== MODEL KARSILASTIRMASI (test seti, esik 0.50) ===")
    table = pd.DataFrame({n: r["test_metrics"] for n, r in results.items()}).T
    print(table[["accuracy", "precision", "recall", "f1", "roc_auc"]].to_string())
    print(f"\nSecilen: {best_name} | Esik: {threshold:.3f}")


if __name__ == "__main__":
    main()
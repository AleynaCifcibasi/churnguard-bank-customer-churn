"""On isleme testleri: temizleme, bolme, sizintisiz donusum."""
import numpy as np
import pandas as pd
import pytest

from src.preprocessing import (
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    build_preprocessor,
    clean_data,
    data_quality_report,
    get_feature_names,
    load_data,
    split_data,
)


def test_clean_data_removes_duplicate_rows_and_ids(customers_df):
    with_duplicates = pd.concat([customers_df, customers_df.head(5)], ignore_index=True)
    cleaned = clean_data(with_duplicates)
    assert len(cleaned) == len(customers_df)
    assert not cleaned["CustomerID"].duplicated().any()


def test_clean_data_does_not_fill_missing_values(customers_df):
    """Eksikler temizlemede doldurulmaz; Pipeline icinde (sizintisiz) doldurulur."""
    df = customers_df.copy()
    df.loc[0, "CreditScore"] = np.nan
    df.loc[1, "Geography"] = None
    cleaned = clean_data(df)
    assert cleaned["CreditScore"].isna().sum() == 1
    assert cleaned["Geography"].isna().sum() == 1


def test_clean_data_drops_rows_without_target(customers_df):
    df = customers_df.copy()
    df.loc[2, "Exited"] = np.nan
    cleaned = clean_data(df)
    assert len(cleaned) == len(df) - 1
    assert cleaned["Exited"].dtype.kind == "i"


def test_split_keeps_class_ratio_and_has_no_overlap(customers_df):
    X_train, X_test, y_train, y_test = split_data(customers_df)
    assert len(X_test) == pytest.approx(len(customers_df) * 0.2, abs=1)
    assert abs(y_train.mean() - y_test.mean()) < 0.02          # stratify
    assert set(X_train.index).isdisjoint(set(X_test.index))     # ayni satir iki tarafta olmaz


def test_features_exclude_id_target_and_segment(customers_df):
    X_train, _, _, _ = split_data(customers_df)
    assert list(X_train.columns) == FEATURE_COLUMNS
    for forbidden in ("CustomerID", "Exited", "CustomerSegment"):
        assert forbidden not in X_train.columns


def test_preprocessor_leaves_no_missing_values(customers_df):
    df = customers_df.copy()
    df.loc[df.index[:10], "CreditScore"] = np.nan
    df.loc[df.index[10:20], "Geography"] = None
    X_train, X_test, _, _ = split_data(df)
    pre = build_preprocessor()
    assert not np.isnan(pre.fit_transform(X_train)).any()
    assert not np.isnan(pre.transform(X_test)).any()


def test_preprocessor_is_fitted_on_training_data_only(customers_df):
    """Veri sizintisi yok: ortalama ve medyan yalnizca egitim verisinden ogrenilir."""
    df = customers_df.copy()
    df.loc[df.index[:30], "CreditScore"] = np.nan
    X_train, _, _, _ = split_data(df)
    pre = build_preprocessor().fit(X_train)
    numeric = pre.named_transformers_["num"]

    age_index = NUMERIC_FEATURES.index("Age")
    assert numeric["scaler"].mean_[age_index] == pytest.approx(X_train["Age"].mean())
    score_index = NUMERIC_FEATURES.index("CreditScore")
    assert numeric["imputer"].statistics_[score_index] == pytest.approx(X_train["CreditScore"].median())


def test_unknown_category_is_ignored_not_crashing(customers_df):
    X_train, X_test, _, _ = split_data(customers_df)
    pre = build_preprocessor().fit(X_train)
    unseen = X_test.head(3).copy()
    unseen["Geography"] = "Mars"
    transformed = pre.transform(unseen)
    geo_columns = [i for i, name in enumerate(get_feature_names(pre)) if name.startswith("Geography_")]
    assert transformed[:, geo_columns].sum() == 0               # bilinmeyen bolge: hepsi 0


def test_feature_names_match_matrix_width(customers_df):
    X_train, _, _, _ = split_data(customers_df)
    pre = build_preprocessor().fit(X_train)
    names = get_feature_names(pre)
    assert len(names) == pre.transform(X_train).shape[1]
    assert "Gender_Female" in names and "NumOfProducts_2" in names


def test_load_data_missing_file_gives_friendly_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="generate_data"):
        load_data(tmp_path / "yok.csv")


def test_load_data_missing_columns_raises(tmp_path):
    path = tmp_path / "eksik.csv"
    pd.DataFrame({"CustomerID": ["A"], "Age": [30]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="eksik sütunlar|eksik sutunlar"):
        load_data(path)


def test_data_quality_report_counts(customers_df):
    df = pd.concat([customers_df, customers_df.head(3)], ignore_index=True)
    df.loc[10, "CreditScore"] = np.nan          # kopyalanan ilk 3 satirin disinda bir satir
    report = data_quality_report(df)
    assert report["n_duplicate_rows"] == 3
    assert report["missing_values"] == {"CreditScore": 1}
    assert report["imbalance_ratio"] > 1
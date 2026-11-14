"""Risk seviyesi hesabi ve esik ayarlari (config.json) testleri."""
import json

import numpy as np
import pytest

from src.config import (
    DEFAULT_RISK_THRESHOLDS,
    load_risk_thresholds,
    save_risk_thresholds,
    validate_risk_thresholds,
)
from src.predict import risk_level, risk_levels

THRESHOLDS = {"low_max": 0.30, "high_min": 0.60}


@pytest.mark.parametrize("probability, expected", [
    (0.0, "low"), (0.2999, "low"),
    (0.30, "medium"), (0.45, "medium"), (0.5999, "medium"),
    (0.60, "high"), (0.95, "high"), (1.0, "high"),
])
def test_risk_level_boundaries(probability, expected):
    assert risk_level(probability, THRESHOLDS) == expected


def test_every_probability_gets_a_level_without_gaps():
    for p in np.linspace(0, 1, 1001):
        assert risk_level(float(p), THRESHOLDS) in {"low", "medium", "high"}


def test_vectorized_version_matches_scalar():
    probabilities = np.linspace(0, 1, 101)
    vector = risk_levels(probabilities, THRESHOLDS)
    assert list(vector) == [risk_level(float(p), THRESHOLDS) for p in probabilities]


def test_custom_thresholds_change_levels():
    custom = {"low_max": 0.50, "high_min": 0.80}
    assert risk_level(0.45, custom) == "low"
    assert risk_level(0.70, custom) == "medium"
    assert risk_level(0.80, custom) == "high"


@pytest.mark.parametrize("low, high", [
    (0.6, 0.3), (0.3, 0.3), (0, 0.5), (0.2, 1), (-0.1, 0.5), ("abc", 0.5), (None, 0.5), (float("nan"), 0.5),
])
def test_invalid_thresholds_are_rejected(low, high):
    with pytest.raises(ValueError):
        validate_risk_thresholds(low, high)


def test_valid_thresholds_accept_numeric_strings():
    assert validate_risk_thresholds("0.25", "0.75") == {"low_max": 0.25, "high_min": 0.75}


def test_load_falls_back_to_defaults_when_file_missing(tmp_path):
    assert load_risk_thresholds(tmp_path / "yok.json") == DEFAULT_RISK_THRESHOLDS


def test_load_falls_back_to_defaults_when_file_corrupt(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ bozuk json", encoding="utf-8")
    assert load_risk_thresholds(path) == DEFAULT_RISK_THRESHOLDS


def test_load_falls_back_when_saved_values_invalid(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"risk_thresholds": {"low_max": 0.9, "high_min": 0.1}}), encoding="utf-8")
    assert load_risk_thresholds(path) == DEFAULT_RISK_THRESHOLDS


def test_save_roundtrip_and_keeps_other_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"baska_ayar": 1}), encoding="utf-8")
    saved = save_risk_thresholds(0.35, 0.65, path)
    assert saved == {"low_max": 0.35, "high_min": 0.65}
    assert load_risk_thresholds(path) == saved
    assert json.loads(path.read_text(encoding="utf-8"))["baska_ayar"] == 1


def test_invalid_save_does_not_touch_the_file(tmp_path):
    path = tmp_path / "config.json"
    save_risk_thresholds(0.3, 0.6, path)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        save_risk_thresholds(0.9, 0.2, path)
    assert path.read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.tmp"))          # gecici dosya kalmamali
"""Girdi dogrulama ve /api/predict ucu testleri."""
import pytest

from src.predict import FEATURE_LABELS, validate_customer_input

ALLOWED = {"Gender": ["Female", "Male"], "Geography": ["Ege", "Marmara", "Ic Anadolu"]}

VALID = {
    "Age": 42, "Gender": "Male", "Geography": "Ege", "CreditScore": 650, "Tenure": 5,
    "Balance": 50000, "NumOfProducts": 2, "HasCrCard": 1, "IsActiveMember": 1,
    "EstimatedSalary": 80000, "Complaints": 0,
}
HIGH_RISK = {**VALID, "Age": 55, "Gender": "Female", "CreditScore": 580, "Tenure": 2, "Balance": 120000,
             "NumOfProducts": 3, "IsActiveMember": 0, "EstimatedSalary": 60000, "Complaints": 2}
LOW_RISK = {**VALID, "Age": 29, "Geography": "Ic Anadolu", "CreditScore": 720, "Tenure": 6,
            "Balance": 85000, "EstimatedSalary": 95000}


# ------------------------------------------------------------ dogrulama (model gerekmez)
def test_validate_accepts_valid_input():
    clean, errors = validate_customer_input(VALID, ALLOWED)
    assert errors == {}
    assert clean["Age"] == 42 and clean["Gender"] == "Male"


def test_validate_accepts_strings_and_case_insensitive_categories():
    payload = {k: str(v) for k, v in VALID.items()}
    payload["Gender"] = "male"
    payload["IsActiveMember"] = "evet"
    clean, errors = validate_customer_input(payload, ALLOWED)
    assert errors == {}
    assert clean["Gender"] == "Male" and clean["IsActiveMember"] == 1


@pytest.mark.parametrize("field, value", [
    ("Age", 17), ("Age", 101), ("Age", 35.5), ("Age", "abc"), ("Age", None), ("Age", ""),
    ("CreditScore", 299), ("CreditScore", 851),
    ("Gender", "X"), ("Geography", "Mars"),
    ("NumOfProducts", 0), ("NumOfProducts", 5),
    ("HasCrCard", 2), ("IsActiveMember", "belki"),
    ("Complaints", -1), ("Balance", -1), ("Tenure", 41),
    ("Balance", float("inf")), ("Balance", float("nan")),
])
def test_validate_rejects_bad_values_and_names_the_field(field, value):
    _, errors = validate_customer_input({**VALID, field: value}, ALLOWED)
    assert list(errors) == [field]
    assert errors[field]                                   # anlasilir bir mesaj var


def test_validate_reports_every_missing_field():
    _, errors = validate_customer_input({}, ALLOWED)
    assert set(errors) == set(FEATURE_LABELS)


# --------------------------------------------------------------------- /api/predict
def test_predict_returns_probability_level_and_disclaimer(client):
    response = client.post("/api/predict", json=HIGH_RISK)
    assert response.status_code == 200
    data = response.get_json()
    assert 0 <= data["probability"] <= 1
    assert data["risk_level"] in {"low", "medium", "high"}
    assert "olasılık" in data["disclaimer"]
    assert 1 <= len(data["factors"]) <= 5


def test_high_risk_customer_scores_higher_than_low_risk_customer(client):
    high = client.post("/api/predict", json=HIGH_RISK).get_json()["probability"]
    low = client.post("/api/predict", json=LOW_RISK).get_json()["probability"]
    assert high > low


def test_predict_accepts_form_strings(client):
    response = client.post("/api/predict", json={k: str(v) for k, v in HIGH_RISK.items()})
    assert response.status_code == 200


def test_predict_invalid_input_returns_422_with_field_errors(client):
    response = client.post("/api/predict", json={**VALID, "Age": 17, "Geography": "Mars"})
    assert response.status_code == 422
    body = response.get_json()
    assert set(body["details"]) == {"Age", "Geography"}
    assert "error" in body


def test_predict_without_json_body_returns_400(client):
    response = client.post("/api/predict", data="merhaba", content_type="text/plain")
    assert response.status_code == 400


def test_predict_rejects_wrong_method(client):
    assert client.get("/api/predict").status_code == 405


# ----------------------------------------------------------------- diger API uclari
def test_health_reports_loaded_model(client):
    data = client.get("/api/health").get_json()
    assert data["status"] == "ok" and data["model_loaded"] is True


def test_dashboard_summary_is_consistent(client):
    data = client.get("/api/dashboard/summary").get_json()
    assert data["total_customers"] == data["churned_customers"] + data["active_customers"]
    assert sum(data["risk_counts_active"].values()) == data["active_customers"]
    assert sum(data["risk_counts_all"].values()) == data["total_customers"]


def test_customers_pagination_and_filters(client):
    page = client.get("/api/customers?per_page=10&page=2").get_json()
    assert len(page["items"]) == 10 and page["page"] == 2
    high = client.get("/api/customers?risk=high&status=active&per_page=50").get_json()
    assert high["total"] > 0
    assert all(c["risk_level"] == "high" and c["exited"] == 0 for c in high["items"])


@pytest.mark.parametrize("query", ["page=abc", "per_page=5000", "risk=extreme", "sort_by=password"])
def test_customers_rejects_bad_query_parameters(client, query):
    response = client.get("/api/customers?" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_customer_detail_found_and_not_found(client):
    first_id = client.get("/api/customers?per_page=1").get_json()["items"][0]["customer_id"]
    found = client.get(f"/api/customers/{first_id}")
    assert found.status_code == 200 and "factors" in found.get_json()
    assert client.get("/api/customers/C999999").status_code == 404
    assert client.get("/api/customers/bad%20id!").status_code in (400, 404)


def test_threshold_preview_does_not_save(client, restore_config):
    before = client.get("/api/settings").get_json()["risk_thresholds"]
    response = client.post("/api/settings/risk-thresholds/preview", json={"low_max": 0.2, "high_min": 0.9})
    assert response.status_code == 200
    assert client.get("/api/settings").get_json()["risk_thresholds"] == before


def test_threshold_update_recalculates_counts(client, restore_config):
    response = client.post("/api/settings/risk-thresholds", json={"low_max": 0.2, "high_min": 0.9})
    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["thresholds"] == {"low_max": 0.2, "high_min": 0.9}
    assert sum(summary["risk_counts_active"].values()) == summary["active_customers"]


def test_threshold_update_rejects_invalid_values(client, restore_config):
    response = client.post("/api/settings/risk-thresholds", json={"low_max": 0.8, "high_min": 0.5})
    assert response.status_code == 422
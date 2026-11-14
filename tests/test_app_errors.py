"""Model/veri olmadiginda ve hatali isteklerde uygulamanin davranisi (model gerekmez)."""
import pytest

from app import Services, create_app

MESSAGE = "Model dosyası bulunamadı. Önce 'python -m src.train' komutunu çalıştırın."


@pytest.fixture
def broken_client():
    """Model yuklenememis bir uygulama."""
    return create_app(Services(error=MESSAGE)).test_client()


def test_health_reports_degraded_state(broken_client):
    response = broken_client.get("/api/health")
    assert response.status_code == 503
    assert response.get_json()["status"] == "degraded"


@pytest.mark.parametrize("path", [
    "/api/dashboard/summary", "/api/dashboard/charts", "/api/customers", "/api/notifications",
])
def test_api_returns_friendly_503_json(broken_client, path):
    response = broken_client.get(path)
    assert response.status_code == 503
    assert response.get_json()["error"] == MESSAGE


def test_predict_returns_503_when_model_missing(broken_client):
    assert broken_client.post("/api/predict", json={}).status_code == 503


@pytest.mark.parametrize("path", ["/dashboard", "/customers", "/prediction", "/reports", "/settings"])
def test_pages_show_help_page_instead_of_crashing(broken_client, path):
    response = broken_client.get(path)
    assert response.status_code == 503
    html = response.get_data(as_text=True)
    assert "Sistem hazır değil" in html and "python -m src.train" in html


def test_unknown_api_path_returns_json_404(broken_client):
    response = broken_client.get("/api/yok")
    assert response.status_code == 404 and "error" in response.get_json()


def test_unknown_page_returns_html_404(broken_client):
    response = broken_client.get("/yok")
    assert response.status_code == 404
    assert "Sayfa bulunamadı" in response.get_data(as_text=True)
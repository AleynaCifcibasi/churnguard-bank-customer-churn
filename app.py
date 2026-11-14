"""Flask uygulamasi: JSON API'leri ve hata yonetimi.

Model burada EGITILMEZ; baslangicta kayitli model ve veri bir kez yuklenir.

Calistirma:
    python app.py        ->  http://127.0.0.1:5000
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from werkzeug.exceptions import HTTPException

from src.analytics import SORT_COLUMNS, CustomerStore, DataNotAvailableError
from src.config import (
    DEFAULT_RISK_THRESHOLDS,
    EXPORTS_DIR,
    load_risk_thresholds,
    save_risk_thresholds,
    validate_risk_thresholds,
)
from src.predict import (
    RISK_LABELS,
    ChurnModel,
    ModelNotAvailableError,
    build_reference_values,
    risk_level,
    validate_customer_input,
)
from src.reports import create_export, list_exports, resolve_export

logger = logging.getLogger("churn_app")

DISCLAIMER = "Bu değer kesin bir sonuç değil, model tahminine dayalı bir olasılıktır."
CUSTOMER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
MAX_PER_PAGE = 100

HTTP_MESSAGES = {
    400: ("Geçersiz istek", "İsteğiniz anlaşılamadı."),
    404: ("Sayfa bulunamadı", "Aradığınız sayfa veya kayıt bulunamadı."),
    405: ("İşleme izin verilmiyor", "Bu adres için yanlış istek türü kullanıldı."),
    500: ("Beklenmeyen hata", "Bir şeyler ters gitti. Lütfen daha sonra tekrar deneyin."),
    503: ("Sistem hazır değil", "Model veya veri dosyaları yüklenemedi."),
}


class ApiError(Exception):
    """Kullaniciya gosterilecek anlasilir hata (HTTP kodu ile birlikte)."""

    def __init__(self, message: str, status: int = 400, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details


@dataclass
class Services:
    model: Optional[ChurnModel] = None
    store: Optional[CustomerStore] = None
    reference: Optional[dict] = None
    error: Optional[str] = None


def load_services() -> Services:
    """Model ve veriyi yukler; basarisiz olursa uygulama cokmez, hata mesajini saklar."""
    try:
        model = ChurnModel()
        store = CustomerStore()
        return Services(model=model, store=store, reference=build_reference_values(store.df))
    except (ModelNotAvailableError, DataNotAvailableError) as exc:
        logger.error("Baslangic hatasi: %s", exc)
        return Services(error=str(exc))


def create_app(services: Optional[Services] = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False       # Turkce karakterler JSON'da bozulmasin
    app.json.sort_keys = False
    app.extensions["services"] = services if services is not None else load_services()

    def get_services() -> Services:
        svc = app.extensions["services"]
        if svc.error:
            raise ApiError(svc.error, status=503)
        return svc

    # ------------------------------------------------------------ Hata yonetimi
    def respond_error(message, status, title=None, details=None):
        if request.path.startswith("/api/"):
            body = {"error": message}
            if details:
                body["details"] = details
            return jsonify(body), status
        default_title = HTTP_MESSAGES.get(status, HTTP_MESSAGES[500])[0]
        hint = "Terminalde 'python -m src.train' komutunu çalıştırıp uygulamayı yeniden başlatın." if status == 503 else None
        return render_template("error.html", code=status, title=title or default_title,
                               message=message, hint=hint), status

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return respond_error(exc.message, exc.status, details=exc.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        title, message = HTTP_MESSAGES.get(exc.code, HTTP_MESSAGES[500])
        return respond_error(message, exc.code, title=title)

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        logger.exception("Beklenmeyen hata")
        title, message = HTTP_MESSAGES[500]
        return respond_error(message, 500, title=title)

    @app.after_request
    def no_cache_for_api(response):
        if request.path.startswith(("/api/", "/exports/")):
            response.headers["Cache-Control"] = "no-store"   # musteri verisi tarayicida saklanmasin
        return response

    # ------------------------------------------------------------------ Sayfalar
    # Menu ogeleri: (rota adi, baslik, ikon). Rotasi henuz olmayan sayfalar menude "Yakinda" gorunur.
    nav_definitions = [
        ("dashboard_page", "Dashboard", "grid"),
        ("customers_page", "Müşteriler", "users"),
        ("prediction_page", "Yeni Müşteri Tahmini", "trending-up"),
        ("reports_page", "Raporlar", "file-text"),
        ("settings_page", "Ayarlar", "sliders"),
    ]

    @app.context_processor
    def inject_navigation():
        items = [
            {"endpoint": endpoint, "label": label, "icon": icon, "enabled": endpoint in app.view_functions}
            for endpoint, label, icon in nav_definitions
        ]
        return {"nav_items": items}

    @app.get("/")
    def index():
        return redirect(url_for("dashboard_page"))

    @app.get("/dashboard")
    def dashboard_page():
        get_services()   # model/veri yoksa anlasilir hata sayfasi gosterilir
        return render_template("dashboard.html", active_page="dashboard_page")

    @app.get("/customers")
    def customers_page():
        get_services()
        return render_template("customers.html", active_page="customers_page")

    @app.get("/prediction")
    def prediction_page():
        svc = get_services()
        return render_template("prediction.html",
                               geographies=svc.model.allowed_categories["Geography"],
                               active_page="prediction_page")

    @app.get("/reports")
    def reports_page():
        get_services()
        return render_template("reports.html", active_page="reports_page")

    @app.get("/settings")
    def settings_page():
        get_services()
        return render_template("settings.html", active_page="settings_page")

    @app.get("/exports/<filename>")
    def download_export(filename):
        path = resolve_export(filename)
        if path is None:
            raise ApiError("Rapor dosyası bulunamadı.", status=404)
        return send_from_directory(EXPORTS_DIR, path.name, as_attachment=True, mimetype="text/csv")

    @app.get("/customers/<customer_id>")
    def customer_detail_page(customer_id):
        get_services()
        if not CUSTOMER_ID_PATTERN.match(customer_id):
            raise ApiError("Geçersiz müşteri numarası.", status=404)
        return render_template("customer_detail.html", customer_id=customer_id, active_page="customers_page")

    @app.get("/api/")
    def api_overview():
        return jsonify({
            "app": "Bank Customer Churn Prediction",
            "endpoints": [
                "GET  /api/health",
                "GET  /api/dashboard/summary",
                "GET  /api/dashboard/charts",
                "GET  /api/customers",
                "GET  /api/customers/<customer_id>",
                "POST /api/predict",
                "GET  /api/settings",
                "POST /api/settings/risk-thresholds",
                "GET  /api/notifications",
            ],
        })

    # ------------------------------------------------------------------- Saglik
    @app.get("/api/health")
    def health():
        svc = app.extensions["services"]
        if svc.error:
            return jsonify({"status": "degraded", "model_loaded": False, "message": svc.error}), 503
        return jsonify({"status": "ok", "model_loaded": True, **svc.model.info(),
                        "n_customers": len(svc.store.df)})

    # ---------------------------------------------------------------- Dashboard
    @app.get("/api/dashboard/summary")
    def dashboard_summary():
        svc = get_services()
        return jsonify(svc.store.summary(load_risk_thresholds()))

    @app.get("/api/dashboard/charts")
    def dashboard_charts():
        svc = get_services()
        return jsonify(svc.store.charts(load_risk_thresholds()))

    @app.get("/api/notifications")
    def notifications():
        svc = get_services()
        return jsonify({"items": svc.store.notifications(load_risk_thresholds())})

    # ----------------------------------------------------------- Musteri listesi
    def parse_int_arg(name, default, minimum=1, maximum=None):
        raw = request.args.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ApiError(f"'{name}' tam sayı olmalıdır.")
        if value < minimum or (maximum is not None and value > maximum):
            limit = f"{minimum}-{maximum}" if maximum else f">= {minimum}"
            raise ApiError(f"'{name}' için geçerli aralık: {limit}.")
        return value

    def parse_choice_arg(name, allowed):
        raw = request.args.get(name)
        if raw is None or raw == "":
            return None
        if raw not in allowed:
            raise ApiError(f"'{name}' şunlardan biri olmalıdır: {', '.join(allowed)}.")
        return raw

    @app.get("/api/customers")
    def customers():
        svc = get_services()
        active_raw = parse_choice_arg("active_member", ["0", "1"])
        sort_by = parse_choice_arg("sort_by", list(SORT_COLUMNS)) or "customer_id"
        sort_order = parse_choice_arg("sort_order", ["asc", "desc"]) or "asc"
        search = (request.args.get("search") or "").strip()[:20]
        result = svc.store.list_customers(
            load_risk_thresholds(),
            page=parse_int_arg("page", 1),
            per_page=parse_int_arg("per_page", 25, maximum=MAX_PER_PAGE),
            search=search or None,
            risk=parse_choice_arg("risk", ["low", "medium", "high"]),
            gender=parse_choice_arg("gender", ["Female", "Male"]),
            segment=parse_choice_arg("segment", ["Standard", "Gold", "Premium"]),
            active_member=int(active_raw) if active_raw is not None else None,
            status=parse_choice_arg("status", ["active", "churned"]),
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return jsonify(result)

    @app.get("/api/customers/<customer_id>")
    def customer_detail(customer_id):
        svc = get_services()
        if not CUSTOMER_ID_PATTERN.match(customer_id):
            raise ApiError("Geçersiz müşteri numarası.", status=400)
        thresholds = load_risk_thresholds()
        customer = svc.store.get_customer(customer_id, thresholds)
        if customer is None:
            raise ApiError("Bu numaraya sahip müşteri bulunamadı.", status=404)
        features = svc.store.get_feature_row(customer_id)
        customer["factors"] = svc.model.explain(features, svc.reference)
        customer["disclaimer"] = DISCLAIMER
        return jsonify(customer)

    # ------------------------------------------------------------------- Tahmin
    @app.post("/api/predict")
    def predict():
        svc = get_services()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ApiError("Geçerli bir JSON gövdesi gönderilmelidir.")
        clean, errors = validate_customer_input(payload, svc.model.allowed_categories)
        if errors:
            raise ApiError("Formda düzeltilmesi gereken alanlar var.", status=422, details=errors)

        thresholds = load_risk_thresholds()
        probability = svc.model.predict_one(clean)
        level = risk_level(probability, thresholds)
        return jsonify({
            "probability": round(probability, 4),
            "probability_pct": round(probability * 100, 1),
            "risk_level": level,
            "risk_label": RISK_LABELS[level],
            "thresholds": thresholds,
            "factors": svc.model.explain(clean, svc.reference),
            "disclaimer": DISCLAIMER,
        })

    # ------------------------------------------------------------------ Raporlar
    @app.post("/api/reports/export")
    def export_report():
        svc = get_services()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ApiError("Geçerli bir JSON gövdesi gönderilmelidir.")
        try:
            result = create_export(svc.store, load_risk_thresholds(),
                                   payload.get("type"), payload.get("format", "excel"))
        except ValueError as exc:
            raise ApiError(str(exc), status=400)
        except OSError:
            logger.exception("Rapor dosyasi yazilamadi")
            raise ApiError("Rapor dosyası yazılamadı. 'exports' klasörüne yazma izni olduğundan ve dosyanın "
                           "başka bir programda açık olmadığından emin olun.", status=500)
        return jsonify(result), 201

    @app.get("/api/reports/exports")
    def report_exports():
        get_services()
        return jsonify({"items": list_exports()})

    # ------------------------------------------------------------------ Ayarlar
    @app.get("/api/settings")
    def get_settings():
        return jsonify({"risk_thresholds": load_risk_thresholds(), "defaults": DEFAULT_RISK_THRESHOLDS})

    @app.post("/api/settings/risk-thresholds")
    def update_thresholds():
        svc = get_services()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "low_max" not in payload or "high_min" not in payload:
            raise ApiError("'low_max' ve 'high_min' alanları gönderilmelidir (0 ile 1 arasında).")
        try:
            thresholds = save_risk_thresholds(payload["low_max"], payload["high_min"])
        except ValueError as exc:
            raise ApiError(str(exc), status=422)
        logger.info("Risk esikleri guncellendi: %s", thresholds)
        return jsonify({
            "risk_thresholds": thresholds,
            "summary": svc.store.summary(thresholds),
        })

    @app.post("/api/settings/risk-thresholds/preview")
    def preview_thresholds():
        """Esikleri KAYDETMEDEN, bu esiklerle risk gruplarinin kac musteriden olusacagini gosterir."""
        svc = get_services()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "low_max" not in payload or "high_min" not in payload:
            raise ApiError("'low_max' ve 'high_min' alanları gönderilmelidir (0 ile 1 arasında).")
        try:
            thresholds = validate_risk_thresholds(payload["low_max"], payload["high_min"])
        except ValueError as exc:
            raise ApiError(str(exc), status=422)
        return jsonify({"risk_thresholds": thresholds, "summary": svc.store.summary(thresholds)})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Yalnizca bu bilgisayardan erisilebilir (127.0.0.1), musteri verisi aga acilmaz.
    create_app().run(host="127.0.0.1", port=5000, debug=False)
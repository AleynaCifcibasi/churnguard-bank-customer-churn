"""CSV raporlari: icerik, indirme ve guvenlik testleri."""
import pandas as pd
import pytest

from src.reports import FILENAME_PATTERN, resolve_export


def _read(path, sep=";", decimal=","):
    return pd.read_csv(path, sep=sep, decimal=decimal, encoding="utf-8-sig")


def test_predictions_export_excel_format(client, export_dir):
    response = client.post("/api/reports/export", json={"type": "predictions", "format": "excel"})
    assert response.status_code == 201
    info = response.get_json()
    assert FILENAME_PATTERN.match(info["filename"])
    path = export_dir / info["filename"]
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")             # Excel icin BOM
    frame = _read(path)
    assert len(frame) == info["rows"] == client.get("/api/health").get_json()["n_customers"]
    assert {"Müşteri ID", "Kayıp Olasılığı (%)", "Risk Seviyesi"} <= set(frame.columns)
    assert frame["Kayıp Olasılığı (%)"].between(0, 100).all()


def test_high_risk_export_contains_only_active_high_risk_sorted(client, export_dir):
    info = client.post("/api/reports/export", json={"type": "high_risk", "format": "standard"}).get_json()
    frame = _read(export_dir / info["filename"], sep=",", decimal=".")
    assert set(frame["Risk Seviyesi"]) == {"Yüksek"}
    assert set(frame["Durum"]) == {"Müşteri"}
    assert frame["Kayıp Olasılığı (%)"].is_monotonic_decreasing


def test_summary_export_has_expected_dimensions(client, export_dir):
    info = client.post("/api/reports/export", json={"type": "summary"}).get_json()
    frame = _read(export_dir / info["filename"])
    assert {"Segment", "Yaş Grubu", "Bölge", "Cinsiyet", "Kredi Kartı"} <= set(frame["Boyut"])
    assert "Güneydoğu Anadolu" in set(frame["Grup"])                  # Turkce karakterli bolge adi


def test_export_can_be_downloaded_and_listed(client, export_dir):
    info = client.post("/api/reports/export", json={"type": "summary"}).get_json()
    download = client.get(info["download_url"])
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]
    assert download.headers["Cache-Control"] == "no-store"
    listed = client.get("/api/reports/exports").get_json()["items"]
    assert info["filename"] in [item["filename"] for item in listed]


def test_two_exports_in_same_second_do_not_overwrite(client, export_dir):
    names = {client.post("/api/reports/export", json={"type": "summary"}).get_json()["filename"] for _ in range(3)}
    assert len(names) == 3


@pytest.mark.parametrize("payload", [{"type": "hepsi"}, {"type": "summary", "format": "pdf"}, {}])
def test_export_rejects_invalid_requests(client, export_dir, payload):
    assert client.post("/api/reports/export", json=payload).status_code == 400
    assert list(export_dir.iterdir()) == []                            # hicbir dosya olusmamali


@pytest.mark.parametrize("name", [
    "../config.json", "..%2Fconfig.json", "tum_tahminler_x.csv", "kayip_ozeti_20260101_000000.csv",
])
def test_download_blocks_traversal_and_unknown_names(client, export_dir, name):
    assert client.get("/exports/" + name).status_code == 404


def test_download_serves_only_files_matching_the_report_name_pattern(client, export_dir):
    """Klasorde gercekten var olan ama rapor kalibina uymayan dosyalar da indirilemez."""
    for name in ("gizli.csv", "config.json", "tum_tahminler_x.csv", "tum_tahminler_20260101_000000.csv.exe"):
        (export_dir / name).write_text("gizli", encoding="utf-8")
        assert client.get("/exports/" + name).status_code == 404, name
    valid = "tum_tahminler_20260101_000000.csv"
    (export_dir / valid).write_text("a;b\n1;2\n", encoding="utf-8")
    assert client.get("/exports/" + valid).status_code == 200


def test_resolve_export_rejects_path_tricks(export_dir):
    assert resolve_export("../app.py") is None
    assert resolve_export("tum_tahminler_20260101_000000.csv") is None   # kalibi dogru ama dosya yok
    (export_dir / "notlar.txt").write_text("x", encoding="utf-8")
    assert resolve_export("notlar.txt") is None                          # dosya var ama kalip uymuyor
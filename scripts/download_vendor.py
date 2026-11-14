"""Bootstrap ve Chart.js dosyalarini bir kez indirip static/vendor/ klasorune koyar.

Calistirma (proje kok klasorunden):
    python scripts/download_vendor.py          # eksik dosyalari indirir
    python scripts/download_vendor.py --force  # hepsini yeniden indirir

Internet yalnizca bu adimda gerekir. Sonrasinda uygulama tamamen cevrimdisi calisir.
"""
import io
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / "static" / "vendor"
URL = "https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"

# (paket, surum, {paket icindeki dosya: static/vendor icindeki ad})
PACKAGES = [
    ("bootstrap", "5.3.3", {
        "package/dist/css/bootstrap.min.css": "bootstrap.min.css",
        "package/dist/js/bootstrap.bundle.min.js": "bootstrap.bundle.min.js",
    }),
    ("chart.js", "4.4.4", {"package/dist/chart.umd.js": "chart.umd.js"}),
]


def download_package(name: str, version: str, files: dict) -> None:
    url = URL.format(name=name, version=version)
    print(f"Indiriliyor: {name} {version} ...")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        sys.exit(f"HATA: {url} indirilemedi ({exc}). Internet baglantisini kontrol edip tekrar deneyin.")

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member_name, target_name in files.items():
            member = archive.extractfile(member_name)
            if member is None:
                sys.exit(f"HATA: {member_name} paketin icinde bulunamadi.")
            content = member.read()
            if not content:
                sys.exit(f"HATA: {member_name} bos geldi.")
            (VENDOR_DIR / target_name).write_bytes(content)
            print(f"  yazildi: static/vendor/{target_name} ({len(content) / 1024:.0f} KB)")


def main() -> None:
    force = "--force" in sys.argv
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    pending = [
        (name, version, files) for name, version, files in PACKAGES
        if force or any(not (VENDOR_DIR / target).exists() for target in files.values())
    ]
    if not pending:
        print("Tum dosyalar zaten mevcut. Yeniden indirmek icin: python scripts/download_vendor.py --force")
        return
    for name, version, files in pending:
        download_package(name, version, files)
    print("Tamam.")


if __name__ == "__main__":
    main()
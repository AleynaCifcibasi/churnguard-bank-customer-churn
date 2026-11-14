# Bank Customer Churn Prediction

Bankaların müşteri kaybını (churn) önceden tahmin etmesine yardımcı olan, makine öğrenmesi destekli, **tamamen yerel (localhost)** çalışan bir web uygulaması.

> **Önemli:** Bu projedeki tüm müşteri verileri **kurgusaldır** (yapay olarak üretilmiştir), gerçek kişilere ait değildir.
> Modelin ürettiği değerler **kesin sonuç değil, olasılık/risk skorudur.**

## Özellikler

- **Dashboard:** toplam / kaybedilen / aktif müşteri, kayıp oranı, yüksek-orta-düşük riskli müşteri sayıları ve 7 etkileşimli grafik
- **Müşteri listesi:** arama, filtreleme, sıralama, sunucu taraflı sayfalama (25 kayıt), müşteri detayı ve "riski etkileyen faktörler"
- **Yeni müşteri tahmini:** doğrulamalı form, yüzde olarak olasılık, risk seviyesi ve renkli gösterge
- **Raporlar:** segment / yaş / bölge / cinsiyet kırılımlı kayıp özeti, yüksek riskli müşteri listesi, CSV dışa aktarma
- **Ayarlar:** risk eşiklerini ekrandan değiştirme (kaydetmeden önce önizleme), model bilgisi
- Model **her istekte eğitilmez**; eğitim ayrı bir adımdır, web uygulaması kayıtlı modeli kullanır
- Model veya veri dosyası yoksa uygulama çökmez, ne yapılacağını söyleyen bir sayfa gösterir

## Teknolojiler

| Katman | Araçlar |
|---|---|
| Backend | Python, Flask, Pandas, NumPy, Scikit-learn, Joblib |
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js (yerel dosyalar, internet gerekmez) |
| Veri | CSV dosyaları (veritabanı yok) |
| Test | pytest |

Test edilen ortam: Python 3.12, Flask 3.1, pandas 3.x, scikit-learn 1.9. Python 3.10+ gerekir.

## Kurulum ve çalıştırma

Tüm komutlar **proje klasörünün içinde** çalıştırılır.

### 1. Sanal ortam oluştur ve etkinleştir

Windows (PowerShell):
```powershell
python -m venv venv
venv\Scripts\activate
```
macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```
Satır başında `(venv)` görmelisin.

### 2. Paketleri kur
```
pip install -r requirements.txt
```

### 3. Bootstrap ve Chart.js dosyalarını indir (yalnızca bir kez, internet gerekir)
```
python scripts/download_vendor.py
```
Bu komut `static/vendor/` klasörüne üç dosya koyar: `bootstrap.min.css`, `bootstrap.bundle.min.js`, `chart.umd.js`. Sonrasında uygulama internetsiz çalışır.

> Betik çalışmazsa dosyaları elle de koyabilirsin: Bootstrap 5.3.3 ("Compiled CSS and JS") ve Chart.js 4.4.4 paketlerinden yukarıdaki üç dosyayı `static/vendor/` içine kopyala.

### 4. Sentetik veriyi üret
```
python src/generate_data.py
```
`data/bank_customers.csv` dosyası oluşur (10.000 satır, sabit seed ile her seferinde aynı veri).

### 5. Modelleri eğit ve en iyisini kaydet
```
python -m src.train
```
Dört model eğitilir ve karşılaştırılır (1–5 dakika sürebilir). Şunlar oluşur:
- `models/churn_model.joblib`: seçilen model, karar eşiği ve meta bilgi
- `models/metrics.json`: karşılaştırma sonuçları
- `data/predictions.csv`: her müşteri için out-of-fold risk olasılığı (dashboard bunu okur)

> Modülleri `python -m src.xxx` biçiminde çalıştırın (`python src/train.py` değil).

### 6. Uygulamayı başlat
```
python app.py
```

### 7. Tarayıcıdan aç
**http://127.0.0.1:5000**

Durdurmak için terminalde `Ctrl + C`. Uygulama yalnızca bu bilgisayardan erişilebilir (`127.0.0.1`).

## Proje yapısı

```
bank-churn-project/
├── app.py                  Flask uygulaması: sayfalar, JSON API'ler, hata yönetimi
├── config.json             Risk seviyesi eşikleri (Ayarlar sayfasından değişir)
├── requirements.txt
├── pytest.ini
├── README.md
├── data/
│   ├── bank_customers.csv  Sentetik müşteri verisi
│   └── predictions.csv     Model tahminleri (eğitimle üretilir)
├── models/
│   ├── churn_model.joblib  Kayıtlı model + eşik + meta bilgi
│   └── metrics.json        Karşılaştırma sonuçları
├── notebooks/
│   ├── exploratory_analysis.ipynb   Veri keşfi
│   └── model_training.ipynb         Eğitim sonuçlarının incelenmesi
├── scripts/
│   └── download_vendor.py  Bootstrap + Chart.js indirici (tek seferlik)
├── src/
│   ├── config.py           Dosya yolları, sabitler, eşik ayarları (okuma/yazma)
│   ├── generate_data.py    Sentetik veri üretimi
│   ├── preprocessing.py    Yükleme, temizleme, ön işleme pipeline'ı, bölme
│   ├── evaluation.py       Metrikler, eşik optimizasyonu, model seçimi
│   ├── train.py            Eğitim, karşılaştırma, kayıt
│   ├── predict.py          Model yükleme, doğrulama, risk seviyesi, açıklama
│   ├── analytics.py        Dashboard ve liste verileri
│   └── reports.py          CSV raporları
├── templates/              HTML şablonları (base, dashboard, customers, ...)
├── static/
│   ├── css/style.css
│   ├── js/                 app.js, dashboard.js, customers.js, ...
│   └── vendor/             Bootstrap ve Chart.js (yerel)
├── tests/                  Birim ve entegrasyon testleri
└── exports/                Oluşturulan CSV raporları
```

## Sayfalar

| Adres | İçerik |
|---|---|
| `/dashboard` | Özet kartlar ve grafikler |
| `/customers` | Müşteri tablosu (arama, filtre, sıralama, sayfalama) |
| `/customers/<ID>` | Müşteri detayı ve risk faktörleri |
| `/prediction` | Yeni müşteri tahmin formu |
| `/reports` | Kayıp özeti, yüksek riskli liste, CSV dışa aktarma |
| `/settings` | Risk eşikleri ve model bilgisi |

## Veri seti (sentetik)

`src/generate_data.py` 10.000 kurgusal müşteri üretir (sabit seed = 42, genel churn oranı yaklaşık %20).

| Sütun | Açıklama |
|---|---|
| `CustomerID` | Kurgusal kimlik (C100001, ...) |
| `Age`, `Gender`, `Geography` | Yaş, cinsiyet, bölge (7 coğrafi bölge) |
| `CreditScore`, `Tenure`, `Balance`, `EstimatedSalary` | Kredi skoru (300–850), müşteri süresi, bakiye, tahmini maaş |
| `NumOfProducts`, `HasCrCard`, `IsActiveMember`, `Complaints` | Ürün sayısı, kredi kartı, aktif üyelik, şikayet sayısı |
| `CustomerSegment` | Kurallı türetme: **Premium** (bakiye ≥ 150.000 veya maaş ≥ 170.000), **Gold** (bakiye ≥ 80.000 veya maaş ≥ 110.000), diğerleri **Standard** |
| `Exited` | Hedef değişken: 1 = bankadan ayrıldı |

Ayrılma olasılığı rastgele değil, mantıklı ilişkilerle üretilir (yaş, 3–4 ürün, pasif üyelik, şikayet ve düşük kredi skoru riski artırır; 2 ürün azaltır) ve bir lojistik fonksiyona gürültü eklenir. Ön işleme adımlarının gerçekten çalıştığını göstermek için veriye bilerek ~%1,5 eksik değer ve 25 tekrar kayıt eklenir.

`CustomerSegment` modele girmez (bakiye ve maaştan türetildiği için yeni bilgi taşımaz), yalnızca dashboard'da gruplama için kullanılır.

## Makine öğrenmesi

**Ön işleme** (tamamı bir `Pipeline` / `ColumnTransformer` içinde, veri sızıntısı olmadan):
- tekrar kayıtlar silinir; eksik değerler **eğitim verisinden öğrenilen** medyan / en sık değerle doldurulur
- sayısal sütunlar `StandardScaler` ile ölçeklenir; kategorik sütunlar `OneHotEncoder` ile kodlanır (`NumOfProducts` etkisi doğrusal olmadığı için kategori sayılır)
- veri, sınıf oranı korunarak %80 eğitim / %20 test olarak bölünür (`stratify`)
- sınıf dengesizliği (~%20 ayrılan) `class_weight='balanced'` (Gradient Boosting için `sample_weight`) ile ele alınır

**Modeller:** Logistic Regression, Decision Tree, Random Forest, Gradient Boosting. Her biri için 5 katlı çapraz doğrulama ile hiperparametre araması (`RandomizedSearchCV`, ölçüt: F1).

**Seçim kuralı:** önce Recall ≥ 0,70 sağlayan modeller, bunlar arasından en yüksek F1 (eşitlikte ROC-AUC).
**Karar eşiği:** seçilen model için, test verisine bakılmadan, eğitim verisinin out-of-fold tahminlerinden precision-recall eğrisi üzerinden belirlenir.

Test seti sonuçları (karar eşiği 0,50; küçük farklarla değişebilir):

| Model | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| Logistic Regression | 0,387 | 0,722 | 0,504 | 0,792 |
| Decision Tree | 0,352 | 0,659 | 0,459 | 0,729 |
| **Random Forest (seçilen)** | 0,402 | 0,720 | 0,516 | 0,787 |
| Gradient Boosting | 0,395 | 0,727 | 0,512 | 0,788 |

Seçilen model, optimize edilen eşikle (≈0,489): Recall ≈ 0,73, Precision ≈ 0,39, F1 ≈ 0,51.

**Nasıl yorumlanır?**
- Modeller birbirine çok yakındır; veri kurgusal ve rastgelelik içerdiği için hiçbir model belli bir sınırın (AUC ≈ 0,79) üstüne çıkamaz. Gerçek veride sonuçlar farklı olur.
- Recall öncelikli olduğu için yüksek riskli denen müşterilerin bir kısmı aslında kalır (Precision ≈ %39). Bu bilinçli bir takastır.
- Dengesizliği düzeltmek için ayrılan müşterilere ağırlık verildiğinden **model yüzdeleri abartılı çıkar** (ortalama %42, gerçek oran %20). Değerler **sıralama için güvenilirdir**: geçmiş veride Düşük risk grubunun ~%4'ü, Orta grubun ~%18'i, Yüksek grubun ~%49'u ayrılmıştır. Arayüz bunu sonuç ekranında ayrıca gösterir.

## Risk seviyeleri

| Seviye | Kayıp olasılığı (varsayılan) |
|---|---|
| Düşük | < %30 |
| Orta | %30 ≤ olasılık < %60 |
| Yüksek | ≥ %60 |

Aralıklar boşluksuzdur. Eşikler **Ayarlar** sayfasından değiştirilebilir ve `config.json` dosyasına kaydedilir (`0 < düşük < yüksek < 1`). Eşik değişince model **yeniden eğitilmez**; dashboard, liste ve raporlar anında yeni eşiklere göre hesaplanır.

"Aktif müşteri", bankada kalan (`Exited = 0`) müşteridir. Risk kartları ve "yüksek riskli" rapor yalnızca bu müşterileri sayar; zaten ayrılmış birine elde tutma kampanyası yapılamaz.

## CSV raporları

**Raporlar** sayfasından üç CSV üretilebilir: *Tüm tahminler*, *Yüksek riskli müşteriler*, *Kayıp özet raporu*. Dosyalar `exports/` klasörüne zaman damgalı adla (`yuksek_riskli_20261114_162443.csv`) yazılır ve tarayıcıdan indirilir.

- **Excel (Türkçe)** biçimi `;` ayracı ve ondalık virgül kullanır; dosyaya çift tıklayınca Excel'de sütunlar düzgün açılır, Türkçe harfler bozulmaz.
- **Standart** biçim `,` ayracı ve ondalık nokta kullanır (Python, veritabanı vb. için).

## API uçları

| Yöntem | Adres | Görev |
|---|---|---|
| GET | `/api/health` | Model durumu ve bilgisi |
| GET | `/api/dashboard/summary` | Kart sayıları |
| GET | `/api/dashboard/charts` | Grafik verileri |
| GET | `/api/customers` | Liste (`page`, `per_page`, `search`, `risk`, `gender`, `segment`, `active_member`, `status`, `sort_by`, `sort_order`) |
| GET | `/api/customers/<ID>` | Müşteri detayı ve faktörler |
| POST | `/api/predict` | Yeni müşteri tahmini |
| GET / POST | `/api/settings`, `/api/settings/risk-thresholds` | Eşikleri oku / kaydet |
| POST | `/api/settings/risk-thresholds/preview` | Kaydetmeden önizleme |
| POST | `/api/reports/export` | CSV oluştur (`type`: predictions / high_risk / summary, `format`: excel / standard) |
| GET | `/api/reports/exports` | Oluşturulan dosyalar |
| GET | `/exports/<dosya>` | CSV indir |

Hatalar uygun HTTP koduyla ve Türkçe mesajla döner (400 hatalı istek, 404 bulunamadı, 422 form hatası, 503 model/veri yok).

## Testler

```
python -m pytest -q
```

Testler ön işleme (temizleme, sızıntısızlık, bölme), risk seviyesi ve eşik ayarları, girdi doğrulama, tahmin ucu, CSV raporları (içerik ve indirme güvenliği) ile model/veri yokken uygulamanın davranışını kapsar. API testleri eğitilmiş modele ihtiyaç duyar; model yoksa o testler atlanır. Testler `config.json`'u ve proje içindeki `exports/` klasörünü değiştirmez.

## Notebook'lar

VS Code'da açıp çalıştırabilir ya da terminalden sonuçlarıyla birlikte üretebilirsin:
```
jupyter nbconvert --to notebook --execute --inplace notebooks/exploratory_analysis.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/model_training.ipynb
```
`model_training.ipynb`, önce `python -m src.train` çalıştırılmış olmasını gerektirir.

## Güvenlik ve gizlilik

- Uygulama yalnızca `127.0.0.1` üzerinde dinler, ağa açılmaz; harici servis ve CDN kullanılmaz.
- Veriler kurgusaldır. Formda girilen müşteri bilgileri kaydedilmez.
- API cevapları ve indirilen dosyalar tarayıcı önbelleğinde tutulmaz (`Cache-Control: no-store`).
- Ekrana yazılan tüm metinler HTML'e karşı temizlenir; tüm girdiler sunucuda yeniden doğrulanır.
- CSV indirme adresi yalnızca rapor adı kalıbına uyan dosyalara cevap verir (yol atlatma denemeleri 404 döner).
- Kimlik doğrulama yoktur; üst çubuktaki kullanıcı alanı yalnızca görseldir.
- Flask'ın geliştirme sunucusu kullanılır; gerçek bir canlı ortam için uygun değildir.

## Sınırlılıklar

- Veri kurgusaldır; gerçek bankacılık verisinde sonuçlar ve model seçimi farklı olur.
- Model yüzdeleri kalibre edilmemiştir (yukarıya bakın).
- "Riski etkileyen faktörler", her özelliği tipik müşteri değeriyle değiştirip olasılığın ne kadar oynadığına bakan bir **model katkısı** açıklamasıdır; neden-sonuç ilişkisi göstermez.
- Eşik ayarı tek kullanıcılı ve kalıcıdır; kimin değiştirdiği kaydedilmez.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| `No module named 'flask'` (veya pandas, sklearn) | Sanal ortam etkin değil: `venv\Scripts\activate`, ardından `pip install -r requirements.txt` |
| Sayfa stilsiz ve grafikler boş | `static/vendor/` boş: `python scripts/download_vendor.py` |
| "Sistem hazır değil" sayfası / 503 | Model veya veri yok: `python src/generate_data.py` ve `python -m src.train` çalıştırıp uygulamayı yeniden başlat |
| `/dashboard` 404 veriyor | Eski bir sunucu çalışıyor: `Ctrl + C` ile durdur, `python app.py` ile yeniden başlat |
| Kod değişikliği görünmüyor | Şablonlar ve `app.py` açılışta yüklenir; sunucuyu yeniden başlat, tarayıcıda `Ctrl + F5` yap |
| `Address already in use` / port 5000 dolu | Başka bir program kullanıyor; onu kapat ya da `app.py` sonundaki `port=5000` değerini değiştir |
| CSV Excel'de tek sütun görünüyor | "Excel (Türkçe)" biçimini seç |
| Terminalde Türkçe harfler bozuk | Yalnızca terminal gösterimi; tarayıcıda ve dosyalarda sorun yok |
| `python src/train.py` hata veriyor | `python -m src.train` biçiminde çalıştır |
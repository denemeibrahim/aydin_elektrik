# Aydın İli Elektrik Tüketim Tahmin Sistemi

## Kurulum

```bash
pip install -r requirements.txt
python app.py
```

Tarayıcıdan aç: http://localhost:5000

## Proje Yapısı

```
aydin_elektrik/
├── app.py              # Flask web sunucusu + API endpoint'leri
├── model.py            # Veri yükleme, özellik mühendisliği, model eğitimi
├── requirements.txt
├── templates/
│   └── index.html      # Modern web arayüzü
├── 2023_verileri.xlsx  # Aylık elektrik tüketim verileri
├── 2024_verileri.xlsx
├── 2025_verileri.xlsx
├── 2023sıcaklık.xlsx   # Günlük hava durumu verileri
├── 2024sıcaklık.xlsx
└── 2025sıcaklık.xlsx
```

## Özellikler

- **3 ML modeli**: Random Forest, Gradient Boosting, Ridge Regression
- **Otomatik model seçimi**: Cross-validation R² skoruna göre
- **Gerçek zamanlı hava verisi**: 7Timer API (fallback: Open-Meteo)
- **Manuel test**: Özel hava koşulları ile tahmin yapabilme
- **Görsel dashboard**: Geçmiş tüketim grafikleri + model karşılaştırması

## API Endpoint'leri

- `GET /api/predict` — Bugünkü tahmin (otomatik hava verisi)
- `GET /api/history` — Geçmiş aylık tüketim verisi
- `POST /api/manual_predict` — Manuel hava verisi ile tahmin
  ```json
  {"tavg": 25, "tmin": 20, "tmax": 32, "prcp": 0, "wspd": 4, "pres": 1013}
  ```

## Notlar

- Hava verisi önce 7Timer API'den çekilir, başarısız olursa Open-Meteo kullanılır
- Model ilk istekte eğitilip önbelleğe alınır (≈2-5 saniye)
- Aylık tüketim tahmini gün sayısına bölünerek günlük tahmine dönüştürülür

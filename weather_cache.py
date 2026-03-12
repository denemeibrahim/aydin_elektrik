"""Hava verisini dosyaya cache'ler - worker'lar arasi paylasim icin"""
import json, os, datetime, requests

CACHE_FILE = "/tmp/weather_cache.json"
CACHE_TTL  = 3600  # 1 saat

AYDIN_LAT = 37.8444
AYDIN_LON = 27.8458

def get_weather():
    # Cache dosyasi var mi ve taze mi?
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            age = datetime.datetime.now().timestamp() - cached.get("_ts", 0)
            if age < CACHE_TTL:
                cached["source"] = "Open-Meteo (cache)"
                return cached, None
        except Exception:
            pass

    # API'ye git
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={AYDIN_LAT}&longitude={AYDIN_LON}"
            f"&daily=temperature_2m_max,temperature_2m_min,"
            f"precipitation_sum,windspeed_10m_max,surface_pressure_mean"
            f"&forecast_days=1&timezone=Europe%2FIstanbul"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        d = resp.json()["daily"]
        tmax = d["temperature_2m_max"][0]
        tmin = d["temperature_2m_min"][0]
        weather = {
            "tavg": round((tmax + tmin) / 2, 1),
            "tmin": tmin,
            "tmax": tmax,
            "prcp": d["precipitation_sum"][0] or 0.0,
            "wspd": d["windspeed_10m_max"][0] or 0.0,
            "pres": round((d.get("surface_pressure_mean") or [1013])[0], 1),
            "source": "Open-Meteo",
            "_ts": datetime.datetime.now().timestamp(),
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(weather, f)
        return weather, None
    except Exception as e:
        # API basarisiz, eski cache varsa kullan
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE) as f:
                    cached = json.load(f)
                cached["source"] = "Open-Meteo (eski cache)"
                return cached, f"API hatasi, eski cache kullanildi: {e}"
            except Exception:
                pass
        # Hicbir sey yoksa varsayilan
        return {
            "tavg": 20.0, "tmin": 15.0, "tmax": 25.0,
            "prcp": 0.0,  "wspd": 4.0,  "pres": 1013.0,
            "source": "Varsayilan (API hatasi)",
        }, str(e)

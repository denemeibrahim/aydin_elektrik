"""Hava verisini dosyaya cache'ler - worker'lar arasi paylasim icin"""
import json, os, datetime, requests

CACHE_FILE = "/tmp/weather_cache.json"
CACHE_TTL  = 3600  # 1 saat

def fetch_from_api():
    """wttr.in - rate limit yok, ucretsiz"""
    try:
        url = "https://wttr.in/Aydin,Turkey?format=j1"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        d = resp.json()
        cur = d["current_condition"][0]
        today = d["weather"][0]
        return {
            "tavg": round((float(today["maxtempC"]) + float(today["mintempC"])) / 2, 1),
            "tmin": float(today["mintempC"]),
            "tmax": float(today["maxtempC"]),
            "prcp": float(today.get("hourly", [{}])[0].get("precipMM", 0)),
            "wspd": float(cur.get("windspeedKmph", 10)) / 3.6,
            "pres": float(cur.get("pressure", 1013)),
            "source": "wttr.in",
        }, None
    except Exception as e:
        return None, str(e)

def get_weather():
    # Cache dosyasi var mi ve taze mi?
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            age = datetime.datetime.now().timestamp() - cached.get("_ts", 0)
            if age < CACHE_TTL:
                data = {k: v for k, v in cached.items() if k != "_ts"}
                data["source"] = cached.get("source", "wttr.in") + " (cache)"
                return data, None
        except Exception:
            pass

    # API'ye git
    weather, err = fetch_from_api()
    if weather:
        to_save = weather.copy()
        to_save["_ts"] = datetime.datetime.now().timestamp()
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(to_save, f)
        except Exception:
            pass
        return weather, None

    # API basarisiz, eski cache varsa kullan
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            data = {k: v for k, v in cached.items() if k != "_ts"}
            data["source"] = "wttr.in (eski cache)"
            return data, f"API hatasi, eski cache: {err}"
        except Exception:
            pass

    # Hicbir sey yoksa Aydin icin mevsimsel varsayilan
    month = datetime.date.today().month
    avg_temps = {1:8,2:9,3:12,4:17,5:22,6:27,7:31,8:31,9:26,10:20,11:14,12:10}
    tavg = avg_temps.get(month, 18)
    return {
        "tavg": float(tavg), "tmin": float(tavg-4), "tmax": float(tavg+4),
        "prcp": 0.0, "wspd": 4.0, "pres": 1013.0,
        "source": "Mevsimsel varsayilan (API hatasi)",
    }, str(err)

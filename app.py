from flask import Flask, render_template, jsonify, request
import requests
import datetime
import os
import traceback

from model import get_trained, predict_today

app = Flask(__name__)

AYDIN_LAT = 37.8444
AYDIN_LON = 27.8458


def fetch_weather_openmeteo():
    """Open-Meteo — ücretsiz, kayıt gerektirmez, doğru Celsius verir"""
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
        tavg = round((tmax + tmin) / 2, 1)
        pres_list = d.get("surface_pressure_mean", [None])
        pres = pres_list[0] if pres_list[0] is not None else 1013.0
        return {
            "tavg": tavg,
            "tmin": tmin,
            "tmax": tmax,
            "prcp": d["precipitation_sum"][0] or 0.0,
            "wspd": d["windspeed_10m_max"][0] or 0.0,
            "pres": round(pres, 1),
            "source": "Open-Meteo",
        }, None
    except Exception as e:
        return None, str(e)


def get_today_weather():
    weather, err = fetch_weather_openmeteo()
    if weather:
        return weather, None
    # Fallback: makul varsayılan değerler
    return {
        "tavg": 20.0, "tmin": 15.0, "tmax": 25.0,
        "prcp": 0.0,  "wspd": 4.0,  "pres": 1013.0,
        "source": "Varsayılan (API hatası)",
    }, f"Open-Meteo erişilemedi: {err}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/predict", methods=["GET"])
def api_predict():
    try:
        trained = get_trained()
        weather, weather_warning = get_today_weather()

        result = predict_today(
            weather_today=weather,
            results=trained["results"],
            best_name=trained["best_name"],
            scaler=trained["scaler"],
            merged_df=trained["merged"],
        )

        stats_out = [
            {
                "name":     mname,
                "cv_r2":    st["cv_r2"],
                "train_r2": st["train_r2"],
                "mae":      st["mae"],
                "rmse":     st["rmse"],
                "mape":     st.get("mape", 0),
                "is_best":  mname == trained["best_name"],
            }
            for mname, st in trained["model_stats"].items()
        ]

        return jsonify({
            "success": True,
            "weather": {
                "tavg":   weather["tavg"],
                "tmin":   weather["tmin"],
                "tmax":   weather["tmax"],
                "prcp":   weather["prcp"],
                "wspd":   weather["wspd"],
                "pres":   weather["pres"],
                "source": weather.get("source", "?"),
            },
            "weather_warning": weather_warning,
            "predictions":     result,
            "model_stats":     stats_out,
            "date":            datetime.date.today().isoformat(),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e),
                        "trace": traceback.format_exc()}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    try:
        merged  = get_trained()["merged"]
        rows    = merged[["year","month","Genel Toplam (MWh)","tavg","tmax","tmin"]].copy()
        records = rows.sort_values(["year","month"]).rename(
            columns={"Genel Toplam (MWh)":"toplam"}
        ).to_dict(orient="records")
        return jsonify({"success": True, "data": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/manual_predict", methods=["POST"])
def manual_predict():
    try:
        body    = request.get_json()
        trained = get_trained()
        result  = predict_today(
            weather_today=body,
            results=trained["results"],
            best_name=trained["best_name"],
            scaler=trained["scaler"],
            merged_df=trained["merged"],
        )
        return jsonify({"success": True, "predictions": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("🔄 Model eğitiliyor...")
    get_trained()
    print("✅ Model hazır!")
    app.run(debug=True, host="0.0.0.0", port=5000)

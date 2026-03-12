from flask import Flask, render_template, jsonify, request
import datetime
import traceback

from model import get_trained, predict_today
from weather_cache import get_weather

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/predict", methods=["GET"])
def api_predict():
    try:
        trained = get_trained()
        weather, weather_warning = get_weather()

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
    print("Model egitiliyor...")
    get_trained()
    print("Model hazir!")
    app.run(debug=True, host="0.0.0.0", port=5000)

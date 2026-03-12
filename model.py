import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score
import warnings, os, calendar

warnings.filterwarnings("ignore")

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
ELEC_YEARS    = [2019,2020,2021,2022,2023,2024,2025]
WEATHER_YEARS = [2019,2020,2021,2022,2023,2024,2025,2026]

# ─── Veri Yükleme ───────────────────────────────────────────────────────────

def load_electricity_data():
    dfs = []
    for year in ELEC_YEARS:
        path = os.path.join(BASE_DIR, f"{year}_verileri.xlsx")
        if not os.path.exists(path): continue
        df  = pd.read_excel(path)
        raw = df["Dönem"].astype(str)
        months = []
        for val in raw:
            val = val.strip()
            if "-" in val or "/" in val:
                try: months.append(pd.to_datetime(val).month); continue
                except: pass
            try:
                num = int(float(val)); s = str(num)
                if   len(s)==5: months.append(int(s[0]))
                elif len(s)==6: months.append(int(s[:2]))
                else:           months.append(None)
            except: months.append(None)
        df["month"] = months
        df["year"]  = year
        dfs.append(df)

    result = pd.concat(dfs, ignore_index=True)
    result = result.dropna(subset=["month"])
    result["month"] = result["month"].astype(int)

    # ── Veri temizliği ──────────────────────────────────────────────────────
    # 2021 Ekim: 76 MWh — açıkça hatalı kayıt, interpolasyonla doldur
    mask = (result["year"]==2021) & (result["month"]==10)
    result.loc[mask, "Genel Toplam (MWh)"] = np.nan

    # 2025 Nisan iki kez "5" olarak girilmiş (ay=5 iki satır), birini Nisan yap
    mask25 = (result["year"]==2025) & (result["month"]==5)
    if mask25.sum() == 2:
        idx = result[mask25].index
        result.loc[idx[0], "month"] = 4   # ilk satırı Nisan yap

    # Tüm NaN tüketim değerlerini aynı ay geçmiş ortalama ile doldur
    for idx in result[result["Genel Toplam (MWh)"].isna()].index:
        m = result.loc[idx, "month"]
        fill = result[(result["month"]==m) & result["Genel Toplam (MWh)"].notna()]["Genel Toplam (MWh)"].mean()
        result.loc[idx, "Genel Toplam (MWh)"] = fill

    return result


def load_weather_data():
    dfs = []
    for year in WEATHER_YEARS:
        path = os.path.join(BASE_DIR, f"{year}sıcaklık.xlsx")
        if not os.path.exists(path): continue
        df = pd.read_excel(path)
        df["date"] = pd.to_datetime(df["date"])
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


def build_monthly_weather(weather_df):
    w = weather_df.copy()
    w["year"]  = w["date"].dt.year
    w["month"] = w["date"].dt.month
    return w.groupby(["year","month"]).agg(
        tavg=("tavg","mean"), tmin=("tmin","mean"), tmax=("tmax","mean"),
        prcp=("prcp","sum"),  wspd=("wspd","mean"), pres=("pres","mean"),
    ).reset_index()


# ─── Özellik Mühendisliği ────────────────────────────────────────────────────

def build_features(elec_df, weather_monthly):
    merged = pd.merge(elec_df, weather_monthly, on=["year","month"], how="inner")
    merged = merged.sort_values(["year","month"]).reset_index(drop=True)

    # Temel
    merged["season"]     = merged["month"].apply(lambda m: 0 if m in [12,1,2] else 1 if m in [3,4,5] else 2 if m in [6,7,8] else 3)
    merged["year_trend"] = merged["year"] - 2019
    merged["hdd"]        = (18 - merged["tavg"]).clip(lower=0)
    merged["cdd"]        = (merged["tavg"] - 18).clip(lower=0)

    # Lag: geçmiş tüketim
    merged["prev_month_consumption"]  = merged["Genel Toplam (MWh)"].shift(1)
    merged["prev2_month_consumption"] = merged["Genel Toplam (MWh)"].shift(2)
    merged["consumption_delta"]       = merged["Genel Toplam (MWh)"].shift(1) - merged["Genel Toplam (MWh)"].shift(2)
    merged["rolling_3m_avg"]          = merged["Genel Toplam (MWh)"].shift(1).rolling(3, min_periods=1).mean()
    merged["rolling_6m_avg"]          = merged["Genel Toplam (MWh)"].shift(1).rolling(6, min_periods=1).mean()

    # Geçen/2 yıl aynı ay
    ly_map = merged.groupby(["year","month"])["Genel Toplam (MWh)"].first().to_dict()
    merged["same_month_last_year"] = merged.apply(lambda r: ly_map.get((r["year"]-1, r["month"]), np.nan), axis=1)
    merged["same_month_2y_ago"]    = merged.apply(lambda r: ly_map.get((r["year"]-2, r["month"]), np.nan), axis=1)
    merged["yoy_growth"]           = (merged["Genel Toplam (MWh)"] / merged["same_month_last_year"] - 1).shift(1)

    # Hava lag
    merged["prev_month_tavg"] = merged["tavg"].shift(1)
    merged["temp_delta"]      = merged["tavg"] - merged["prev_month_tavg"]

    # Etkileşim
    merged["temp_x_month"] = merged["tavg"] * merged["month"]
    merged["cdd_x_prev"]   = merged["cdd"] * merged["prev_month_consumption"].fillna(merged["prev_month_consumption"].median())

    # Bayraklar
    merged["is_transition_month"] = merged["month"].apply(lambda m: 1 if m in [5,6,9,10] else 0)
    merged["is_peak_summer"]      = merged["month"].apply(lambda m: 1 if m in [7,8] else 0)
    merged["is_winter"]           = merged["month"].apply(lambda m: 1 if m in [12,1,2] else 0)

    lag_cols = ["prev_month_consumption","prev2_month_consumption","consumption_delta",
                "rolling_3m_avg","rolling_6m_avg","same_month_last_year","same_month_2y_ago",
                "yoy_growth","prev_month_tavg","temp_delta","cdd_x_prev"]
    for col in lag_cols:
        merged[col] = merged[col].fillna(merged[col].median())

    return merged


FEATURE_COLS = [
    "month","season","year_trend",
    "tavg","tmin","tmax","prcp","wspd","pres",
    "hdd","cdd",
    "prev_month_consumption","prev2_month_consumption",
    "rolling_3m_avg","rolling_6m_avg",
    "same_month_last_year","same_month_2y_ago",
    "consumption_delta","yoy_growth",
    "prev_month_tavg","temp_delta",
    "temp_x_month","cdd_x_prev",
    "is_transition_month","is_peak_summer","is_winter",
]


# ─── Model Eğitimi ───────────────────────────────────────────────────────────

def train_models(merged_df):
    X = merged_df[FEATURE_COLS].fillna(merged_df[FEATURE_COLS].median())
    y = merged_df["Genel Toplam (MWh)"]
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    cv_folds = min(7, len(X))

    models = {
        "Random Forest":     RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=5, max_features=0.6, random_state=42),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=100, learning_rate=0.08, max_depth=2, subsample=0.5, min_samples_leaf=6, max_features=0.6, random_state=42),
        "Ridge Regression":  Ridge(alpha=3.0),
    }

    results = {}; best_name, best_score = None, -np.inf
    for name, model in models.items():
        is_scaled = (name == "Ridge Regression")
        Xf = X_scaled if is_scaled else X

        # CV R² (k-fold)
        cv_scores = cross_val_score(model, Xf, y, cv=cv_folds, scoring="r2")
        cv_r2 = cv_scores.mean()

        # Modeli tüm veriyle eğit
        model.fit(Xf, y)
        yp       = model.predict(Xf)
        train_r2 = r2_score(y, yp)
        mae      = mean_absolute_error(y, yp)
        rmse     = np.sqrt(mean_squared_error(y, yp))
        mape     = np.mean(np.abs((y.values - yp) / y.values) * 100)

        results[name] = {
            "model":     model,
            "cv_r2":     round(cv_r2, 4),
            "train_r2":  round(train_r2, 4),
            "mae":       round(mae, 2),
            "rmse":      round(rmse, 2),
            "mape":      round(mape, 2),
            "is_scaled": is_scaled,
        }
        if cv_r2 > best_score: best_score=cv_r2; best_name=name
    return results, best_name, scaler


# ─── Bugünkü Tahmin ──────────────────────────────────────────────────────────

def predict_today(weather_today: dict, results: dict, best_name: str, scaler, merged_df):
    import datetime
    today  = datetime.date.today()
    month  = today.month; year = today.year
    season = 0 if month in [12,1,2] else 1 if month in [3,4,5] else 2 if month in [6,7,8] else 3
    tavg   = weather_today.get("tavg", 20.0)

    def gc(y,m):
        r = merged_df[(merged_df["year"]==y)&(merged_df["month"]==m)]
        return r["Genel Toplam (MWh)"].values[0] if len(r) else merged_df["Genel Toplam (MWh)"].median()
    def gt(y,m):
        r = merged_df[(merged_df["year"]==y)&(merged_df["month"]==m)]
        return r["tavg"].values[0] if len(r) else tavg

    pm=month-1 if month>1 else 12; py=year  if month>1 else year-1
    pm2=pm-1   if pm>1    else 12; py2=py   if pm>1    else py-1

    prev_cons=gc(py,pm); prev2_cons=gc(py2,pm2); prev_tavg=gt(py,pm)
    ly_cons=gc(year-1,month); ly2_cons=gc(year-2,month)
    roll3 = merged_df.sort_values(["year","month"]).tail(3)["Genel Toplam (MWh)"].mean()
    roll6 = merged_df.sort_values(["year","month"]).tail(6)["Genel Toplam (MWh)"].mean()
    yoy   = (gc(year-1,month)/gc(year-2,month)-1) if gc(year-2,month) else 0
    cdd   = max(tavg-18,0)

    row = {
        "month":month,"season":season,"year_trend":year-2019,
        "tavg":tavg,"tmin":weather_today.get("tmin",tavg-3),
        "tmax":weather_today.get("tmax",tavg+3),
        "prcp":weather_today.get("prcp",0),"wspd":weather_today.get("wspd",5),
        "pres":weather_today.get("pres",1013),
        "hdd":max(18-tavg,0),"cdd":cdd,
        "prev_month_consumption":prev_cons,"prev2_month_consumption":prev2_cons,
        "rolling_3m_avg":roll3,"rolling_6m_avg":roll6,
        "same_month_last_year":ly_cons,"same_month_2y_ago":ly2_cons,
        "consumption_delta":prev_cons-prev2_cons,"yoy_growth":yoy,
        "prev_month_tavg":prev_tavg,"temp_delta":tavg-prev_tavg,
        "temp_x_month":tavg*month,"cdd_x_prev":cdd*prev_cons,
        "is_transition_month":1 if month in [5,6,9,10] else 0,
        "is_peak_summer":1 if month in [7,8] else 0,
        "is_winter":1 if month in [12,1,2] else 0,
    }

    X_row = pd.DataFrame([row])[FEATURE_COLS]
    X_s   = scaler.transform(X_row)
    predictions = {
        name: round(info["model"].predict(X_s if info["is_scaled"] else X_row)[0], 2)
        for name,info in results.items()
    }

    days_in_month = calendar.monthrange(year,month)[1]
    daily_preds   = {k:round(v/days_in_month,2) for k,v in predictions.items()}
    best_daily    = daily_preds[best_name]

    same_month_rows = merged_df[merged_df["month"]==month]["Genel Toplam (MWh)"]
    hist_monthly    = round(same_month_rows.mean(),2) if len(same_month_rows) else None
    hist_daily      = round(hist_monthly/days_in_month,2) if hist_monthly else None
    hist_diff_pct   = round((best_daily - hist_daily) / hist_daily * 100, 1) if hist_daily else None

    ly_days      = calendar.monthrange(year-1, month)[1]
    ly_daily     = round(ly_cons / ly_days, 2) if ly_cons else None
    ly_diff_pct  = round((best_daily - ly_daily) / ly_daily * 100, 1) if ly_daily else None

    ly2_days     = calendar.monthrange(year-2, month)[1]
    ly2_daily    = round(ly2_cons / ly2_days, 2) if ly2_cons else None
    ly2_diff_pct = round((best_daily - ly2_daily) / ly2_daily * 100, 1) if ly2_daily else None

    return {
        "monthly_predictions":    predictions,
        "daily_predictions":      daily_preds,
        "best_model":             best_name,
        "best_daily":             best_daily,
        "historical_monthly_avg": hist_monthly,
        "historical_daily_avg":   hist_daily,
        "hist_diff_pct":          hist_diff_pct,
        "ly_year":                year - 1,
        "ly_daily":               ly_daily,
        "ly_diff_pct":            ly_diff_pct,
        "ly2_year":               year - 2,
        "ly2_daily":              ly2_daily,
        "ly2_diff_pct":           ly2_diff_pct,
        "days_in_month":          days_in_month,
        "month":                  month,
        "year":                   year,
        "input_weather":          row,
    }


# ─── Global Cache ────────────────────────────────────────────────────────────

_cache = {}

def get_trained():
    if "data" not in _cache:
        elec   = load_electricity_data()
        weather= load_weather_data()
        wm     = build_monthly_weather(weather)
        merged = build_features(elec, wm)
        results, best_name, scaler = train_models(merged)
        _cache["data"] = {
            "results":results,"best_name":best_name,"scaler":scaler,
            "feature_cols":FEATURE_COLS,"merged":merged,
            "model_stats":{name:{k:v for k,v in info.items() if k!="model"} for name,info in results.items()},
        }
    return _cache["data"]

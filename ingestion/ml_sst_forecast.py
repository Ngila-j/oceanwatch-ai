"""
OceanWatch AI — Production SST Forecasting
Naive vs Ridge vs GradientBoosting | temporal split | MAE/RMSE | joblib artifacts
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("/opt/airflow/models/sst") if Path("/opt/airflow").exists() else Path("models/sst")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "sst_lag_1", "sst_lag_2", "sst_lag_3", "sst_lag_7", "sst_lag_14",
    "sst_roll_mean_3", "sst_roll_mean_7", "sst_roll_mean_14",
    "sst_roll_std_3", "sst_roll_std_7",
    "day_of_year", "month", "sin_doy", "cos_doy",
]


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def load_sst_series(con) -> pd.DataFrame:
    df = con.execute("""
        SELECT date_key::date AS date, sst_celsius AS mean_sst
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
    """).fetchdf()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["mean_sst"] = df["mean_sst"].astype(float)
    for lag in [1, 2, 3, 7, 14]:
        df[f"sst_lag_{lag}"] = df["mean_sst"].shift(lag)
    for w in [3, 7, 14]:
        df[f"sst_roll_mean_{w}"] = df["mean_sst"].rolling(w).mean()
    for w in [3, 7]:
        df[f"sst_roll_std_{w}"] = df["mean_sst"].rolling(w).std()
    df["day_of_year"] = df["date"].dt.dayofyear
    df["month"] = df["date"].dt.month
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)
    return df


def temporal_split(df: pd.DataFrame, test_days: int = 5):
    if len(df) <= test_days + 10:
        test_days = max(1, len(df) // 5)
    return df.iloc[:-test_days].copy(), df.iloc[-test_days:].copy()


def mae(y_true, y_pred):
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


def evaluate_naive(train, test):
    last = float(train["mean_sst"].iloc[-1])
    preds = [last] * len(test)
    return {"model": "naive_persistence", "mae": mae(test["mean_sst"], preds),
            "rmse": rmse(test["mean_sst"], preds), "predictions": preds}


def _fit_sklearn(train, test, feature_cols, model_name, model):
    from sklearn.preprocessing import StandardScaler

    train_c = train.dropna(subset=feature_cols + ["mean_sst"])
    test_c = test.dropna(subset=feature_cols + ["mean_sst"])
    if len(train_c) < 8 or len(test_c) < 1:
        return None

    scaler = StandardScaler()
    X_train = scaler.fit_transform(train_c[feature_cols])
    y_train = train_c["mean_sst"].values
    X_test = scaler.transform(test_c[feature_cols])
    y_test = test_c["mean_sst"].values

    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    return {
        "model": model_name,
        "mae": mae(y_test, preds),
        "rmse": rmse(y_test, preds),
        "predictions": preds.tolist(),
        "model_obj": model,
        "scaler": scaler,
        "feature_cols": feature_cols,
    }


def evaluate_ridge(train, test, feature_cols):
    try:
        from sklearn.linear_model import Ridge
    except ImportError:
        return None
    return _fit_sklearn(train, test, feature_cols, "ridge_lags", Ridge(alpha=1.0))


def evaluate_gbr(train, test, feature_cols):
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        return None
    model = GradientBoostingRegressor(
        n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42
    )
    return _fit_sklearn(train, test, feature_cols, "gradient_boosting", model)


def recursive_forecast(df: pd.DataFrame, best: dict, horizon: int = 7):
    history = df[["date", "mean_sst"]].copy()
    last_date = history["date"].max()
    forecasts = []

    if best["model"] == "naive_persistence":
        last_val = float(history["mean_sst"].iloc[-1])
        for d in range(1, horizon + 1):
            forecasts.append({
                "forecast_for_date": (last_date + timedelta(days=d)).date(),
                "predicted_sst": round(last_val, 3),
                "lower_bound": round(last_val - 0.2 * d, 3),
                "upper_bound": round(last_val + 0.2 * d, 3),
            })
        return forecasts

    model, scaler = best["model_obj"], best["scaler"]
    feature_cols = best["feature_cols"]
    series = history["mean_sst"].tolist()
    dates = list(history["date"])

    for d in range(1, horizon + 1):
        temp = engineer_features(pd.DataFrame({"date": dates, "mean_sst": series}))
        row = temp.iloc[[-1]].copy()
        for c in feature_cols:
            if c not in row or pd.isna(row[c].iloc[0]):
                row[c] = series[-1]
        X = scaler.transform(row[feature_cols])
        pred = float(model.predict(X)[0])
        unc = 0.12 * d
        next_date = last_date + timedelta(days=d)
        forecasts.append({
            "forecast_for_date": next_date.date(),
            "predicted_sst": round(pred, 3),
            "lower_bound": round(pred - unc, 3),
            "upper_bound": round(pred + unc, 3),
        })
        series.append(pred)
        dates.append(next_date)
    return forecasts


def run_pipeline():
    logger.info("=== Production SST Forecasting Pipeline Started ===")
    try:
        import joblib
    except ImportError:
        joblib = None
        logger.warning("joblib not available — model files will not be saved")

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_sst_forecast (
            forecast_date DATE, forecast_for_date DATE, horizon_day INTEGER,
            predicted_sst DOUBLE, lower_bound DOUBLE, upper_bound DOUBLE,
            model_name VARCHAR, model_version VARCHAR, mae DOUBLE, rmse DOUBLE,
            created_at TIMESTAMP
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.ml_model_metrics (
            model_name VARCHAR, target VARCHAR, mae DOUBLE, rmse DOUBLE,
            train_rows INTEGER, test_rows INTEGER, is_best BOOLEAN, trained_at TIMESTAMP
        );
    """)

    raw = load_sst_series(con)
    if raw.empty or len(raw) < 8:
        logger.warning(f"Insufficient SST history ({len(raw)} rows).")
        con.close()
        return

    logger.info(f"Loaded {len(raw)} SST observations")
    feat = engineer_features(raw)
    train, test = temporal_split(feat)
    logger.info(f"Train: {len(train)} | Test: {len(test)}")

    results = [evaluate_naive(train, test)]
    logger.info(f"Naive MAE={results[0]['mae']:.4f}")

    for fn in (evaluate_ridge, evaluate_gbr):
        r = fn(train, test, FEATURE_COLS)
        if r:
            results.append(r)
            logger.info(f"{r['model']} MAE={r['mae']:.4f}")

    best = min(results, key=lambda r: r["mae"])
    logger.info(f"Best: {best['model']} MAE={best['mae']:.4f}")

    # Save joblib
    if joblib and best.get("model_obj") is not None:
        joblib.dump({
            "model": best["model_obj"],
            "scaler": best["scaler"],
            "feature_cols": best["feature_cols"],
            "model_name": best["model"],
        }, ARTIFACT_DIR / "sst_model.joblib")
        logger.info(f"Saved model → {ARTIFACT_DIR / 'sst_model.joblib'}")

    metrics_payload = {
        "target": "mean_sst",
        "forecast_horizon_days": 7,
        "models": [{"model": r["model"], "mae": r["mae"], "rmse": r["rmse"]} for r in results],
        "best_model": best["model"],
        "best_mae": best["mae"],
        "best_rmse": best["rmse"],
        "train_rows": len(train),
        "test_rows": len(test),
        "training_end": str(train["date"].max().date()),
        "generated_at": datetime.utcnow().isoformat(),
    }
    (ARTIFACT_DIR / "model_metrics.json").write_text(json.dumps(metrics_payload, indent=2))

    con.execute("DELETE FROM pg.public.ml_model_metrics;")
    for r in results:
        is_best = "TRUE" if r["model"] == best["model"] else "FALSE"
        con.execute(f"""
            INSERT INTO pg.public.ml_model_metrics VALUES
            ('{r["model"]}', 'mean_sst', {r['mae']}, {r['rmse']},
             {len(train)}, {len(test)}, {is_best}, current_timestamp)
        """)

    forecasts = recursive_forecast(feat.dropna(subset=["mean_sst"]), best, horizon=7)
    now = datetime.utcnow()
    rows = [{
        "forecast_date": now.date(),
        "forecast_for_date": f["forecast_for_date"],
        "horizon_day": i,
        "predicted_sst": f["predicted_sst"],
        "lower_bound": f["lower_bound"],
        "upper_bound": f["upper_bound"],
        "model_name": best["model"],
        "model_version": "v2",
        "mae": best["mae"],
        "rmse": best["rmse"],
        "created_at": now,
    } for i, f in enumerate(forecasts, 1)]

    fdf = pd.DataFrame(rows)
    con.execute("DELETE FROM pg.public.fact_sst_forecast WHERE forecast_date = current_date;")
    con.register("fdf", fdf)
    con.execute("INSERT INTO pg.public.fact_sst_forecast SELECT * FROM fdf;")
    logger.info(f"Wrote {len(fdf)} forecast rows")
    con.close()
    print(json.dumps(metrics_payload, indent=2))
    logger.info("=== SST Forecasting completed ===")


if __name__ == "__main__":
    run_pipeline()
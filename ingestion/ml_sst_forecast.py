"""
OceanWatch AI — Production SST Forecasting Pipeline
- Feature engineering (lags, rolling, calendar)
- Models: Naive baseline + Ridge (sklearn)
- Temporal train/test split
- MAE / RMSE evaluation
- Writes forecasts + metrics to Postgres
- Saves metrics JSON for the dashboard
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

# Paths (work both in container and on host)
ARTIFACT_DIR = Path("/opt/airflow/models/sst") if Path("/opt/airflow").exists() else Path("models/sst")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


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
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lags, rolling stats, calendar features."""
    df = df.copy()
    df["mean_sst"] = df["mean_sst"].astype(float)

    for lag in [1, 2, 3, 7]:
        df[f"sst_lag_{lag}"] = df["mean_sst"].shift(lag)

    for w in [3, 7]:
        df[f"sst_roll_mean_{w}"] = df["mean_sst"].rolling(w).mean()
        df[f"sst_roll_std_{w}"] = df["mean_sst"].rolling(w).std()

    df["day_of_year"] = df["date"].dt.dayofyear
    df["month"] = df["date"].dt.month
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)

    return df


def temporal_split(df: pd.DataFrame, test_days: int = 3):
    """Last N days = test; rest = train. No shuffle."""
    if len(df) <= test_days + 5:
        test_days = max(1, len(df) // 4)
    train = df.iloc[:-test_days].copy()
    test = df.iloc[-test_days:].copy()
    return train, test


def mae(y_true, y_pred):
    return float(np.mean(np.abs(np.array(y_true) - np.array(y_pred))))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((np.array(y_true) - np.array(y_pred)) ** 2)))


def evaluate_naive(train, test):
    """Naive: forecast = last observed value (persistence)."""
    last = train["mean_sst"].iloc[-1]
    preds = [last] * len(test)
    return {
        "model": "naive_persistence",
        "mae": mae(test["mean_sst"], preds),
        "rmse": rmse(test["mean_sst"], preds),
        "predictions": preds,
    }


def evaluate_ridge(train, test, feature_cols):
    """Ridge regression on lag/rolling/calendar features."""
    try:
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        logger.warning("sklearn not available — skipping Ridge model")
        return None

    train_c = train.dropna(subset=feature_cols + ["mean_sst"])
    test_c = test.dropna(subset=feature_cols + ["mean_sst"])
    if len(train_c) < 5 or len(test_c) < 1:
        return None

    scaler = StandardScaler()
    X_train = scaler.fit_transform(train_c[feature_cols])
    y_train = train_c["mean_sst"].values
    X_test = scaler.transform(test_c[feature_cols])
    y_test = test_c["mean_sst"].values

    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    return {
        "model": "ridge_lags",
        "mae": mae(y_test, preds),
        "rmse": rmse(y_test, preds),
        "predictions": preds.tolist(),
        "model_obj": model,
        "scaler": scaler,
        "feature_cols": feature_cols,
    }


def recursive_forecast(df, model_result, horizon=7):
    """Generate horizon-day forecast using the best model."""
    feature_cols = [
        "sst_lag_1", "sst_lag_2", "sst_lag_3", "sst_lag_7",
        "sst_roll_mean_3", "sst_roll_mean_7", "sst_roll_std_3", "sst_roll_std_7",
        "day_of_year", "month", "sin_doy", "cos_doy",
    ]

    history = df[["date", "mean_sst"]].copy()
    last_date = history["date"].max()
    forecasts = []

    if model_result["model"] == "naive_persistence":
        last_val = history["mean_sst"].iloc[-1]
        for d in range(1, horizon + 1):
            forecasts.append({
                "forecast_for_date": (last_date + timedelta(days=d)).date(),
                "predicted_sst": round(float(last_val), 3),
                "lower_bound": round(float(last_val - 0.2 * d), 3),
                "upper_bound": round(float(last_val + 0.2 * d), 3),
            })
        return forecasts

    # Ridge recursive
    model = model_result["model_obj"]
    scaler = model_result["scaler"]
    series = history["mean_sst"].tolist()
    dates = list(history["date"])

    for d in range(1, horizon + 1):
        temp = pd.DataFrame({"date": dates, "mean_sst": series})
        temp = engineer_features(temp)
        row = temp.iloc[[-1]]
        # fill any remaining NaN from short history
        row = row.fillna(method="ffill", axis=1).fillna(series[-1])
        X = scaler.transform(row[feature_cols])
        pred = float(model.predict(X)[0])
        uncertainty = 0.12 * d

        next_date = last_date + timedelta(days=d)
        forecasts.append({
            "forecast_for_date": next_date.date(),
            "predicted_sst": round(pred, 3),
            "lower_bound": round(pred - uncertainty, 3),
            "upper_bound": round(pred + uncertainty, 3),
        })
        series.append(pred)
        dates.append(next_date)

    return forecasts


def run_pipeline():
    logger.info("=== Production SST Forecasting Pipeline Started ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    # Tables
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_sst_forecast (
            forecast_date DATE,
            forecast_for_date DATE,
            horizon_day INTEGER,
            predicted_sst DOUBLE,
            lower_bound DOUBLE,
            upper_bound DOUBLE,
            model_name VARCHAR,
            model_version VARCHAR,
            mae DOUBLE,
            rmse DOUBLE,
            created_at TIMESTAMP
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.ml_model_metrics (
            model_name VARCHAR,
            target VARCHAR,
            mae DOUBLE,
            rmse DOUBLE,
            train_rows INTEGER,
            test_rows INTEGER,
            is_best BOOLEAN,
            trained_at TIMESTAMP
        );
    """)

    raw = load_sst_series(con)
    if raw.empty or len(raw) < 5:
        logger.warning(f"Insufficient SST history ({len(raw)} rows). Need more Copernicus data.")
        con.close()
        return

    logger.info(f"Loaded {len(raw)} SST observations")
    feat = engineer_features(raw)
    train, test = temporal_split(feat, test_days=min(3, max(1, len(feat) // 5)))
    logger.info(f"Train: {len(train)} rows | Test: {len(test)} rows")

    feature_cols = [
        "sst_lag_1", "sst_lag_2", "sst_lag_3", "sst_lag_7",
        "sst_roll_mean_3", "sst_roll_mean_7", "sst_roll_std_3", "sst_roll_std_7",
        "day_of_year", "month", "sin_doy", "cos_doy",
    ]

    results = []
    naive = evaluate_naive(train, test)
    results.append(naive)
    logger.info(f"Naive  MAE={naive['mae']:.4f}  RMSE={naive['rmse']:.4f}")

    ridge = evaluate_ridge(train, test, feature_cols)
    if ridge:
        results.append(ridge)
        logger.info(f"Ridge  MAE={ridge['mae']:.4f}  RMSE={ridge['rmse']:.4f}")

    # Select best by MAE
    best = min(results, key=lambda r: r["mae"])
    logger.info(f"Best model: {best['model']} (MAE={best['mae']:.4f})")

    # Save metrics JSON
    metrics_payload = {
        "target": "mean_sst",
        "forecast_horizon_days": 7,
        "models": [
            {"model": r["model"], "mae": r["mae"], "rmse": r["rmse"]}
            for r in results
        ],
        "best_model": best["model"],
        "best_mae": best["mae"],
        "best_rmse": best["rmse"],
        "train_rows": len(train),
        "test_rows": len(test),
        "training_end": str(train["date"].max().date()) if len(train) else None,
        "generated_at": datetime.utcnow().isoformat(),
    }
    metrics_path = ARTIFACT_DIR / "model_metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, indent=2))
    logger.info(f"Saved metrics → {metrics_path}")

    # Write metrics to DB
    con.execute("DELETE FROM pg.public.ml_model_metrics;")
    for r in results:
        con.execute(f"""
            INSERT INTO pg.public.ml_model_metrics
            VALUES ('{r["model"]}', 'mean_sst', {r['mae']}, {r['rmse']},
                    {len(train)}, {len(test)},
                    {'TRUE' if r['model'] == best['model'] else 'FALSE'},
                    current_timestamp)
        """)

    # Forecast
    forecasts = recursive_forecast(feat.dropna(subset=["mean_sst"]), best, horizon=7)
    now = datetime.utcnow()
    rows = []
    for i, f in enumerate(forecasts, start=1):
        rows.append({
            "forecast_date": now.date(),
            "forecast_for_date": f["forecast_for_date"],
            "horizon_day": i,
            "predicted_sst": f["predicted_sst"],
            "lower_bound": f["lower_bound"],
            "upper_bound": f["upper_bound"],
            "model_name": best["model"],
            "model_version": "v1",
            "mae": best["mae"],
            "rmse": best["rmse"],
            "created_at": now,
        })

    fdf = pd.DataFrame(rows)
    con.execute("DELETE FROM pg.public.fact_sst_forecast WHERE forecast_date = current_date;")
    con.register("fdf", fdf)
    con.execute("INSERT INTO pg.public.fact_sst_forecast SELECT * FROM fdf;")
    logger.info(f"Wrote {len(fdf)} forecast rows")

    con.close()
    logger.info("=== SST Forecasting Pipeline completed ===")
    print(json.dumps(metrics_payload, indent=2))


if __name__ == "__main__":
    run_pipeline()
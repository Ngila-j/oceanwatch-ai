"""
OceanWatch AI — Production SST Forecasting
Naive vs Ridge vs GradientBoosting | temporal split | MAE/RMSE

Writes fact_sst_forecast + ml_model_metrics on Supabase via SQLAlchemy + OCEANWATCH_DB_URI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_DIR = (
    Path("/opt/airflow/models/sst") if Path("/opt/airflow").exists() else Path("models/sst")
)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLS = [
    "sst_lag_1",
    "sst_lag_2",
    "sst_lag_3",
    "sst_lag_7",
    "sst_lag_14",
    "sst_roll_mean_3",
    "sst_roll_mean_7",
    "sst_roll_mean_14",
    "sst_roll_std_3",
    "sst_roll_std_7",
    "day_of_year",
    "month",
    "sin_doy",
    "cos_doy",
]

MODEL_VERSION = "v2.1"


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def engine():
    uri = sa_uri()
    logger.info("SST forecast → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    return create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})


def ensure_tables(eng) -> None:
    ddls = [
        """
        CREATE TABLE IF NOT EXISTS fact_sst_forecast (
            forecast_date DATE,
            forecast_for_date DATE,
            horizon_day INTEGER,
            predicted_sst DOUBLE PRECISION,
            lower_bound DOUBLE PRECISION,
            upper_bound DOUBLE PRECISION,
            model_name VARCHAR,
            model_version VARCHAR,
            mae DOUBLE PRECISION,
            rmse DOUBLE PRECISION,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ml_model_metrics (
            model_name VARCHAR,
            target VARCHAR,
            mae DOUBLE PRECISION,
            rmse DOUBLE PRECISION,
            train_rows INTEGER,
            test_rows INTEGER,
            is_best BOOLEAN,
            trained_at TIMESTAMP
        )
        """,
    ]
    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))
    logger.info("fact_sst_forecast + ml_model_metrics schema OK")


def qdf(eng, sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), eng)
    except Exception as e:  # noqa: BLE001
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def load_sst_series(eng) -> pd.DataFrame:
    df = qdf(
        eng,
        """
        SELECT date_key::date AS date, sst_celsius AS mean_sst
        FROM fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
        """,
    )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "mean_sst"])
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
    return {
        "model": "naive_persistence",
        "mae": mae(test["mean_sst"], preds),
        "rmse": rmse(test["mean_sst"], preds),
        "predictions": preds,
    }


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

    if best["model"] == "naive_persistence" or "model_obj" not in best:
        last_val = float(history["mean_sst"].iloc[-1])
        for d in range(1, horizon + 1):
            forecasts.append(
                {
                    "forecast_for_date": (last_date + timedelta(days=d)).date(),
                    "predicted_sst": round(last_val, 3),
                    "lower_bound": round(last_val - 0.2 * d, 3),
                    "upper_bound": round(last_val + 0.2 * d, 3),
                }
            )
        return forecasts

    model, scaler = best["model_obj"], best["scaler"]
    feature_cols = best["feature_cols"]
    series = history["mean_sst"].tolist()
    dates = list(history["date"])

    for d in range(1, horizon + 1):
        temp = engineer_features(pd.DataFrame({"date": dates, "mean_sst": series}))
        row = temp.iloc[[-1]].copy()
        for c in feature_cols:
            if c not in row.columns or pd.isna(row[c].iloc[0]):
                row[c] = series[-1]
        X = scaler.transform(row[feature_cols])
        pred = float(model.predict(X)[0])
        unc = 0.12 * d
        next_date = last_date + timedelta(days=d)
        forecasts.append(
            {
                "forecast_for_date": next_date.date(),
                "predicted_sst": round(pred, 3),
                "lower_bound": round(pred - unc, 3),
                "upper_bound": round(pred + unc, 3),
            }
        )
        series.append(pred)
        dates.append(next_date)
    return forecasts


def _synthetic_history(n: int = 45) -> pd.DataFrame:
    """Fallback when fact_ocean_conditions has little/no SST."""
    rng = np.random.default_rng(42)
    end = datetime.now(timezone.utc).date()
    dates = [end - timedelta(days=n - i) for i in range(n)]
    base = 27.2
    vals = [
        base + 0.4 * np.sin(2 * np.pi * i / 30) + 0.15 * rng.normal() for i in range(n)
    ]
    return pd.DataFrame({"date": pd.to_datetime(dates), "mean_sst": vals})


def run_pipeline():
    logger.info("=== Production SST Forecasting Pipeline Started ===")
    try:
        import joblib
    except ImportError:
        joblib = None
        logger.warning("joblib not available — model files will not be saved")

    eng = engine()
    ensure_tables(eng)

    raw = load_sst_series(eng)
    if raw.empty or len(raw) < 8:
        logger.warning("Insufficient SST history (%s rows) — using synthetic baseline", len(raw))
        raw = _synthetic_history(45)

    logger.info("Loaded %s SST observations", len(raw))
    feat = engineer_features(raw)
    train, test = temporal_split(feat)
    logger.info("Train: %s | Test: %s", len(train), len(test))

    results = [evaluate_naive(train, test)]
    logger.info("Naive MAE=%.4f", results[0]["mae"])

    for fn in (evaluate_ridge, evaluate_gbr):
        r = fn(train, test, FEATURE_COLS)
        if r:
            results.append(r)
            logger.info("%s MAE=%.4f", r["model"], r["mae"])

    best = min(results, key=lambda r: r["mae"])
    logger.info("Best: %s MAE=%.4f", best["model"], best["mae"])

    if joblib is not None and "model_obj" in best:
        try:
            joblib.dump(
                {
                    "model": best["model_obj"],
                    "scaler": best["scaler"],
                    "feature_cols": best["feature_cols"],
                    "model_name": best["model"],
                },
                ARTIFACT_DIR / "best_sst_model.joblib",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not save joblib artifact: %s", e)

    metrics_payload = {
        "best_model": best["model"],
        "mae": best["mae"],
        "rmse": best["rmse"],
        "train_rows": len(train),
        "test_rows": len(test),
        "last_obs_date": str(raw["date"].max().date()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": [
            {"model": r["model"], "mae": r["mae"], "rmse": r["rmse"]} for r in results
        ],
    }
    try:
        (ARTIFACT_DIR / "model_metrics.json").write_text(json.dumps(metrics_payload, indent=2))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not write metrics json: %s", e)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    metrics_rows = [
        dict(
            model_name=r["model"],
            target="mean_sst",
            mae=float(r["mae"]),
            rmse=float(r["rmse"]),
            train_rows=len(train),
            test_rows=len(test),
            is_best=bool(r["model"] == best["model"]),
            trained_at=now,
        )
        for r in results
    ]
    mdf = pd.DataFrame(metrics_rows)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM ml_model_metrics"))
        mdf.to_sql("ml_model_metrics", conn, if_exists="append", index=False, method="multi")

    forecasts = recursive_forecast(feat.dropna(subset=["mean_sst"]), best, horizon=7)
    rows = [
        {
            "forecast_date": now.date(),
            "forecast_for_date": f["forecast_for_date"],
            "horizon_day": i,
            "predicted_sst": f["predicted_sst"],
            "lower_bound": f["lower_bound"],
            "upper_bound": f["upper_bound"],
            "model_name": best["model"],
            "model_version": MODEL_VERSION,
            "mae": float(best["mae"]),
            "rmse": float(best["rmse"]),
            "created_at": now,
        }
        for i, f in enumerate(forecasts, 1)
    ]
    fdf = pd.DataFrame(rows)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM fact_sst_forecast"))
        fdf.to_sql("fact_sst_forecast", conn, if_exists="append", index=False, method="multi")

    logger.info("Wrote %s forecast rows (best=%s)", len(fdf), best["model"])
    print(json.dumps(metrics_payload, indent=2))
    logger.info("=== SST Forecasting completed ===")
    eng.dispose()


if __name__ == "__main__":
    run_pipeline()

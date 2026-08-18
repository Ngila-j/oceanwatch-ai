"""
OceanWatch AI — Phase 8 REST API
Read-only access to Phase 6/7 products stored in PostgreSQL.
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

import os

DB_URI = os.getenv(
    "OCEANWATCH_DB_URI",
    "postgresql://postgres:password@postgres:5432/oceanwatch_db",
)

# Host machine default when not in Docker
if not os.path.exists("/.dockerenv") and "postgres:5432" in DB_URI:
    DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"

engine = create_engine(DB_URI, pool_pre_ping=True)

app = FastAPI(
    title="OceanWatch AI API",
    description=(
        "Western Indian Ocean / Kenya EEZ monitoring API. "
        "Exposes ocean conditions, SST forecasts, operational alerts, "
        "port risk, vessel anomalies, bloom/habitat scores, and "
        "Global Fishing Watch effort summaries. "
        "Fishing effort data powered by Global Fishing Watch (non-commercial)."
    ),
    version="0.8.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def rows(sql: str, params: Optional[dict] = None):
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, r)) for r in result.fetchall()]


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "oceanwatch-api", "db": "up"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"db down: {e}")


@app.get("/")
def root():
    return {
        "service": "OceanWatch AI API",
        "version": "0.8.1",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/v1/ocean/conditions",
            "/v1/forecasts/sst",
            "/v1/alerts",
            "/v1/port/risk",
            "/v1/gfw/effort/summary",
            "/v1/ml/metrics",
            "/v1/vessels/anomalies",
            "/v1/bloom/risk",
            "/v1/habitat/suitability",
        ],
    }


@app.get("/v1/ocean/conditions")
def ocean_conditions(limit: int = Query(30, ge=1, le=365)):
    data = rows(
        """
        SELECT date_key, location_key, sst_celsius, chlorophyll_mg_m3,
               tide_mean_m, tide_min_m, tide_max_m, loaded_at
        FROM fact_ocean_conditions
        ORDER BY date_key DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    return {"count": len(data), "results": data}


@app.get("/v1/forecasts/sst")
def sst_forecast():
    data = rows(
        """
        SELECT forecast_for_date, horizon_day, predicted_sst,
               lower_bound, upper_bound, model_name, mae
        FROM fact_sst_forecast
        ORDER BY horizon_day
        """
    )
    return {"count": len(data), "results": data}


@app.get("/v1/alerts")
def alerts(
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = None,
):
    if severity:
        data = rows(
            """
            SELECT * FROM fact_alerts
            WHERE UPPER(severity) = UPPER(:severity)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"severity": severity, "limit": limit},
        )
    else:
        data = rows(
            """
            SELECT * FROM fact_alerts
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
    return {"count": len(data), "results": data}


@app.get("/v1/port/risk")
def port_risk():
    data = rows(
        """
        SELECT * FROM fact_port_risk
        ORDER BY risk_date DESC
        LIMIT 5
        """
    )
    return {"count": len(data), "results": data}


@app.get("/v1/gfw/effort/summary")
def gfw_summary():
    data = rows(
        """
        SELECT
            COUNT(*) AS cells,
            COALESCE(SUM(hours), 0) AS total_hours,
            COUNT(DISTINCT effort_date) AS days,
            MIN(effort_date) AS start_date,
            MAX(effort_date) AS end_date
        FROM fact_gfw_fishing_effort
        """
    )
    return {
        "attribution": "Powered by Global Fishing Watch — https://globalfishingwatch.org",
        "summary": data[0] if data else {},
    }


@app.get("/v1/ml/metrics")
def ml_metrics():
    data = rows(
        """
        SELECT model_name, target, mae, rmse, train_rows, test_rows, is_best, trained_at
        FROM ml_model_metrics
        ORDER BY trained_at DESC
        """
    )
    return {"count": len(data), "results": data}


@app.get("/v1/vessels/anomalies")
def vessel_anomalies(limit: int = Query(20, ge=1, le=100)):
    data = rows(
        """
        SELECT vessel_name, vessel_type, risk_score, confidence_score, status, evidence
        FROM fact_vessel_anomalies
        ORDER BY risk_score DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    return {
        "count": len(data),
        "results": data,
        "disclaimer": "Potential anomaly only — not a determination of illegality.",
    }


@app.get("/v1/bloom/risk")
def bloom_risk():
    data = rows(
        """
        SELECT * FROM fact_bloom_risk
        ORDER BY risk_date DESC
        LIMIT 5
        """
    )
    return {"count": len(data), "results": data}


@app.get("/v1/habitat/suitability")
def habitat_suitability():
    data = rows(
        """
        SELECT * FROM fact_habitat_suitability
        ORDER BY as_of_date DESC
        LIMIT 5
        """
    )
    return {"count": len(data), "results": data}
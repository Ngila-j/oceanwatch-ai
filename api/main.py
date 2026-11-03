"""
OceanWatch AI — REST API (Phase 8–10)
Read-only access to Phase 6–9 products stored in PostgreSQL.
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
        "port risk, vessel anomalies, bloom/habitat scores, GFW effort, "
        "and WIO-OII index summaries. "
        "Fishing effort data powered by Global Fishing Watch (non-commercial)."
    ),
    version="0.11.0",
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
        "version": "0.11.0",
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
            "/v1/wio/index",
            "/v1/situation",
            "/v1/coverage/countries",
        ],
        "access_tiers": {
            "public": ["ocean conditions summaries", "health"],
            "research": ["forecasts", "gfw summary", "ml metrics", "wio index"],
            "agency": ["alerts", "port risk", "vessel anomalies"],
            "note": (
                "Tier labels describe the product model. "
                "Full IAM, API keys, and metering are not enforced yet."
            ),
        },
        "commercial": {
            "saas": "Agency dashboards (planned)",
            "api": "Partner API access (planned metering)",
            "reports": "Weekly Ocean Brief PDF",
            "grants": "Blue Economy / climate adaptation framing",
        },
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


@app.get("/v1/wio/index")
def wio_index(limit: int = Query(5, ge=1, le=30)):
    """Latest Western Indian Ocean Ocean Intelligence Index rows."""
    data = rows(
        """
        SELECT
            index_date,
            region_id,
            ocean_health_score,
            maritime_activity_score,
            fishing_pressure_score,
            port_risk_score,
            environmental_risk_score,
            overall_score,
            confidence_score,
            drivers,
            methodology_version,
            created_at
        FROM fact_wio_intelligence_index
        ORDER BY index_date DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    return {
        "count": len(data),
        "results": data,
        "note": "Prototype index with documented weights — not an official government score.",
    }


@app.get("/v1/situation")
def situation(
    lookback_h: int = Query(24, ge=1, le=168),
    region: str = Query("KE", min_length=2, max_length=8),
):
    """
    Fused multi-domain situation snapshot for partners / dashboards.
    Best-effort counts; missing tables yield zeros.
    """
    def _count(sql: str) -> int:
        try:
            with engine.connect() as conn:
                return int(conn.execute(text(sql)).scalar() or 0)
        except Exception:
            return 0

    def _max(sql: str):
        try:
            with engine.connect() as conn:
                v = conn.execute(text(sql)).scalar()
                return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)
        except Exception:
            return None

    metrics = {
        "events": _count(
            f"SELECT COUNT(*) FROM fact_events WHERE COALESCE(created_at, event_time, ts) >= NOW() - INTERVAL '{int(lookback_h)} hours'"
        ),
        "notifications_pending": _count(
            "SELECT COUNT(*) FROM fact_notifications WHERE LOWER(COALESCE(status,'')) IN ('pending','queued','failed','retry')"
        ),
        "risk_elevated": _count(
            "SELECT COUNT(*) FROM unified_risk WHERE LOWER(COALESCE(tier, risk_level, '')) IN ('high','critical','severe')"
        ),
        "anomalies": _count(
            f"SELECT COUNT(*) FROM fact_vessel_anomalies WHERE COALESCE(detected_at, ts, created_at) >= NOW() - INTERVAL '{int(lookback_h)} hours'"
        ),
        "countries": _count("SELECT COUNT(*) FROM dim_countries"),
        "sources": _count("SELECT COUNT(*) FROM dim_data_sources"),
    }
    elevated = metrics["risk_elevated"] + metrics["notifications_pending"]
    posture = "HEIGHTENED" if elevated >= 10 else ("WATCH" if elevated >= 1 else "CALM")
    return {
        "region": region,
        "lookback_h": lookback_h,
        "posture": posture,
        "metrics": metrics,
        "freshness": {
            "events": _max("SELECT MAX(COALESCE(created_at, event_time, ts)) FROM fact_events"),
            "ais": _max("SELECT MAX(COALESCE(ts, base_date_time, created_at)) FROM fact_ais_positions"),
            "risk": _max("SELECT MAX(COALESCE(as_of, updated_at, created_at)) FROM unified_risk"),
        },
        "disclaimer": "Decision-support only — not an official authority product.",
    }


@app.get("/v1/coverage/countries")
def coverage_countries():
    """Regional coverage hierarchy countries (Phase 18)."""
    try:
        data = rows(
            """
            SELECT * FROM dim_countries
            ORDER BY country_id
            """
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"dim_countries unavailable: {e}")
    return {"count": len(data), "results": data}


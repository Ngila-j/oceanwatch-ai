"""Streamlit app configuration (env-overridable)."""

from __future__ import annotations

import os

DB_URI = (
    os.getenv("OCEANWATCH_DB_URI")
    or os.getenv("DATABASE_URL")
    or "postgresql://postgres:password@localhost:5433/oceanwatch_db"
)
API_BASE = os.getenv("OCEANWATCH_API_BASE", "http://localhost:8000")

ROLES = [
    "admin",
    "port_operator",
    "fisheries_user",
    "maritime_user",
    "environment_user",
    "researcher",
    "public",
]

ACCESS_LEVELS = {
    "public": "PUBLIC",
    "researcher": "PUBLIC",
    "environment_user": "RESTRICTED",
    "fisheries_user": "RESTRICTED",
    "port_operator": "RESTRICTED",
    "maritime_user": "SENSITIVE",
    "admin": "SENSITIVE",
}

PUBLIC_DATASETS = [
    "fact_ocean_conditions",
    "fact_sst_forecast",
    "fact_gfw_fishing_effort",
    "ml_model_metrics",
]

RESTRICTED_DATASETS = [
    "fact_port_metrics",
    "fact_port_risk",
    "fact_bloom_risk",
    "fact_habitat_suitability",
    "fact_alerts",
]

SENSITIVE_DATASETS = [
    "fact_ais_positions",
    "fact_vessel_anomalies",
]

# Event bus defaults used by the Streamlit viewer
EVENT_BUS_PAGE_SIZE = 500
EVENT_BUS_CACHE_TTL_SEC = 45

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
API_BASE = "http://localhost:8000"

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
"""
OceanWatch AI — Vessel Behaviour Anomaly Detection
Isolation Forest on AIS-derived behavioural features.
Output: risk scores + evidence → fact_vessel_anomalies + fact_alerts
Language: potential anomalous behaviour / requires human review (not "illegal").
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("/opt/airflow/models/vessel") if Path("/opt/airflow").exists() else Path("models/vessel")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def load_ais(con) -> pd.DataFrame:
    df = con.execute("""
        SELECT mmsi, vessel_name, vessel_type, flag_country,
               latitude, longitude, sog, cog, heading, nav_status, event_time
        FROM pg.public.fact_ais_positions
        ORDER BY mmsi, event_time
    """).fetchdf()
    if not df.empty:
        df["event_time"] = pd.to_datetime(df["event_time"])
    return df


def engineer_vessel_features(df: pd.DataFrame) -> pd.DataFrame:
    """Per-vessel behavioural features from AIS tracks."""
    if df.empty:
        return pd.DataFrame()

    rows = []
    for mmsi, g in df.groupby("mmsi"):
        g = g.sort_values("event_time")
        if len(g) < 3:
            continue

        sog = g["sog"].astype(float)
        cog = g["cog"].astype(float)
        lat = g["latitude"].astype(float)
        lon = g["longitude"].astype(float)

        # Heading / course change
        cog_diff = cog.diff().abs()
        cog_diff = cog_diff.apply(lambda x: min(x, 360 - x) if pd.notnull(x) else np.nan)

        # Distance proxy (degrees → rough km)
        dlat = lat.diff().abs()
        dlon = lon.diff().abs()
        dist_km = ((dlat ** 2 + dlon ** 2) ** 0.5) * 111.0

        speed_mean = float(sog.mean())
        speed_std = float(sog.std() or 0)
        speed_min = float(sog.min())
        low_speed_ratio = float((sog < 3.0).mean())
        turn_rate = float(cog_diff.mean() or 0)
        turn_std = float(cog_diff.std() or 0)
        distance_travelled = float(dist_km.sum())
        track_efficiency = float(dist_km.sum() / (len(g) + 1e-6))  # km per ping
        time_span_h = (g["event_time"].max() - g["event_time"].min()).total_seconds() / 3600.0

        # Boundary proximity (monitoring box edges)
        near_boundary = float(
            ((lat < -4.5) | (lat > 1.5) | (lon < 39.5) | (lon > 44.5)).mean()
        )

        row = {
            "mmsi": mmsi,
            "vessel_name": g["vessel_name"].iloc[-1],
            "vessel_type": g["vessel_type"].iloc[-1],
            "flag_country": g["flag_country"].iloc[-1],
            "last_lat": float(lat.iloc[-1]),
            "last_lon": float(lon.iloc[-1]),
            "n_positions": len(g),
            "speed_mean": speed_mean,
            "speed_std": speed_std,
            "speed_min": speed_min,
            "low_speed_ratio": low_speed_ratio,
            "turn_rate": turn_rate,
            "turn_std": turn_std,
            "distance_travelled_km": distance_travelled,
            "track_efficiency": track_efficiency,
            "time_span_h": time_span_h,
            "near_boundary_ratio": near_boundary,
            "engaged_fishing": int((g["nav_status"] == "Engaged in fishing").any()),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def run_isolation_forest(features: pd.DataFrame):
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    feature_cols = [
        "speed_mean", "speed_std", "speed_min", "low_speed_ratio",
        "turn_rate", "turn_std", "distance_travelled_km",
        "track_efficiency", "time_span_h", "near_boundary_ratio",
        "engaged_fishing",
    ]

    X = features[feature_cols].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # contamination ~ expected anomaly rate
    clf = IsolationForest(
        n_estimators=200,
        contamination=0.15,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_scaled)

    # decision_function: higher = more normal; we invert to risk score 0-100
    raw_scores = clf.decision_function(X_scaled)
    # Map to 0-100 risk (low decision_function → high risk)
    risk = 1 / (1 + np.exp(raw_scores * 5))  # sigmoid-ish
    risk = (risk - risk.min()) / (risk.max() - risk.min() + 1e-9) * 100

    labels = clf.predict(X_scaled)  # -1 anomaly, 1 normal

    features = features.copy()
    features["anomaly_label"] = labels
    features["risk_score"] = np.round(risk, 1)
    features["confidence_score"] = np.round(50 + (100 - risk) * 0.3, 1)

    return features, clf, scaler, feature_cols


def build_evidence(row) -> str:
    reasons = []
    if row["low_speed_ratio"] > 0.5:
        reasons.append("Prolonged low-speed movement")
    if row["turn_rate"] > 25:
        reasons.append("Repeated / high turning behaviour")
    if row["near_boundary_ratio"] > 0.3:
        reasons.append("Activity near monitoring-box boundary")
    if row["engaged_fishing"] == 1:
        reasons.append("Nav status: engaged in fishing")
    if row["speed_std"] > 4:
        reasons.append("High speed variability")
    if row["track_efficiency"] < 0.5:
        reasons.append("Low track efficiency (possible loitering)")
    if not reasons:
        reasons.append("Combined behavioural pattern flagged by model")
    return " | ".join(reasons)


def run_pipeline():
    logger.info("=== Vessel Anomaly Detection Pipeline Started ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_vessel_anomalies (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            risk_score DOUBLE,
            confidence_score DOUBLE,
            anomaly_flag INTEGER,
            evidence VARCHAR,
            status VARCHAR,
            n_positions INTEGER,
            model_name VARCHAR,
            created_at TIMESTAMP
        );
    """)

    ais = load_ais(con)
    if ais.empty:
        logger.warning("No AIS data. Run seed_ais_sample.py first.")
        con.close()
        return

    logger.info(f"Loaded {len(ais)} AIS positions, {ais['mmsi'].nunique()} vessels")
    features = engineer_vessel_features(ais)
    if features.empty or len(features) < 5:
        logger.warning("Not enough vessels for anomaly model")
        con.close()
        return

    scored, clf, scaler, feature_cols = run_isolation_forest(features)
    scored["evidence"] = scored.apply(build_evidence, axis=1)
    scored["status"] = scored["risk_score"].apply(
        lambda r: "REQUIRES_HUMAN_REVIEW" if r >= 60 else "MONITOR"
    )
    scored["anomaly_flag"] = (scored["anomaly_label"] == -1).astype(int)

    now = datetime.utcnow()
    out = pd.DataFrame({
        "mmsi": scored["mmsi"],
        "vessel_name": scored["vessel_name"],
        "vessel_type": scored["vessel_type"],
        "flag_country": scored["flag_country"],
        "latitude": scored["last_lat"],
        "longitude": scored["last_lon"],
        "risk_score": scored["risk_score"],
        "confidence_score": scored["confidence_score"],
        "anomaly_flag": scored["anomaly_flag"],
        "evidence": scored["evidence"],
        "status": scored["status"],
        "n_positions": scored["n_positions"],
        "model_name": "isolation_forest_v1",
        "created_at": now,
    })

    con.execute("DELETE FROM pg.public.fact_vessel_anomalies;")
    con.register("anom_df", out)
    con.execute("INSERT INTO pg.public.fact_vessel_anomalies SELECT * FROM anom_df;")
    logger.info(f"Wrote {len(out)} vessel anomaly rows")

    # Push high-risk into central fact_alerts
    high = out[out["risk_score"] >= 65]
    alerts = []
    for _, row in high.iterrows():
        alerts.append({
            "alert_id": int(np.random.randint(100000, 999999)),
            "alert_type": "VESSEL_ANOMALY",
            "category": "FISHING",
            "severity": "ELEVATED" if row["risk_score"] >= 75 else "WATCH",
            "created_at": now,
            "detected_at": now,
            "location_label": f"{row['latitude']:.3f}, {row['longitude']:.3f}",
            "vessel_name": row["vessel_name"],
            "confidence_score": float(row["confidence_score"]),
            "risk_score": float(row["risk_score"]),
            "title": "Potential Anomalous Vessel Behaviour",
            "description": (
                f"Risk score {row['risk_score']}/100. "
                f"Status: Requires human review. Not classified as illegal activity."
            ),
            "evidence": row["evidence"],
            "status": "OPEN",
            "resolved_at": None,
        })

    if alerts:
        # Ensure fact_alerts exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS pg.public.fact_alerts (
                alert_id INTEGER,
                alert_type VARCHAR,
                category VARCHAR,
                severity VARCHAR,
                created_at TIMESTAMP,
                detected_at TIMESTAMP,
                location_label VARCHAR,
                vessel_name VARCHAR,
                confidence_score DOUBLE,
                risk_score DOUBLE,
                title VARCHAR,
                description VARCHAR,
                evidence VARCHAR,
                status VARCHAR,
                resolved_at TIMESTAMP
            );
        """)
        adf = pd.DataFrame(alerts)
        con.register("alert_df", adf)
        con.execute("INSERT INTO pg.public.fact_alerts SELECT * FROM alert_df;")
        logger.info(f"Inserted {len(alerts)} vessel anomaly alerts")

    # Save metrics artifact
    metrics = {
        "model": "isolation_forest_v1",
        "n_vessels": len(out),
        "n_flagged_anomaly": int(out["anomaly_flag"].sum()),
        "n_high_risk": int((out["risk_score"] >= 65).sum()),
        "feature_cols": feature_cols,
        "generated_at": now.isoformat(),
    }
    (ARTIFACT_DIR / "anomaly_metrics.json").write_text(json.dumps(metrics, indent=2))
    logger.info(f"Metrics: {metrics}")

    con.close()
    logger.info("=== Vessel Anomaly Detection completed ===")


if __name__ == "__main__":
    run_pipeline()
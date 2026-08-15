import os
import logging
from datetime import datetime, timedelta
import json
import random
import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def run_engine():
    logger.info("=== OceanWatch Operational Intelligence Engine Started ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    now = datetime.utcnow()
    alerts = []
    anomalies = []
    port_metrics = []
    fishing_risks = []

    # =========================================================
    # 1. COASTAL RISK (SST + Chlorophyll with baselines)
    # =========================================================
    sst_df = con.execute("""
        SELECT date_key, sst_celsius
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
    """).fetchdf()

    chl_df = con.execute("""
        SELECT date_key, chlorophyll_mg_m3
        FROM pg.public.fact_ocean_conditions
        WHERE chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key
    """).fetchdf()

    def process_metric(df, value_col, metric_name):
        if df.empty or len(df) < 1:
            return
        df = df.copy()
        df["date_key"] = pd.to_datetime(df["date_key"])
        latest = df.iloc[-1]
        current = float(latest[value_col])
        date_key = latest["date_key"].date()

        mean_7d = df[value_col].tail(7).mean() if len(df) >= 1 else current
        mean_30d = df[value_col].tail(30).mean() if len(df) >= 1 else current
        anomaly_val = current - mean_30d
        anomaly_pct = (anomaly_val / mean_30d * 100) if mean_30d != 0 else 0

        if metric_name == "SST":
            if current >= 30 or anomaly_pct >= 8:
                severity = "CRITICAL"
            elif current >= 29 or anomaly_pct >= 5:
                severity = "ELEVATED"
            elif current >= 27.5 or anomaly_pct >= 3:
                severity = "WATCH"
            else:
                severity = "NORMAL"
        else:  # CHL
            if current >= 1.5 or anomaly_pct >= 80:
                severity = "ELEVATED"
            elif current >= 0.8 or anomaly_pct >= 40:
                severity = "WATCH"
            else:
                severity = "NORMAL"

        anomalies.append({
            "anomaly_id": random.randint(10000, 99999),
            "date_key": date_key,
            "metric": metric_name,
            "current_value": current,
            "mean_7d": float(mean_7d),
            "mean_30d": float(mean_30d),
            "anomaly_value": float(anomaly_val),
            "anomaly_pct": float(anomaly_pct),
            "severity": severity,
            "created_at": now
        })

        if severity in ("WATCH", "ELEVATED", "CRITICAL"):
            evidence = {
                "current": round(current, 3),
                "mean_7d": round(float(mean_7d), 3),
                "mean_30d": round(float(mean_30d), 3),
                "anomaly_pct": round(float(anomaly_pct), 2)
            }
            alerts.append({
                "alert_id": random.randint(100000, 999999),
                "alert_type": f"{metric_name}_ANOMALY",
                "category": "COASTAL",
                "severity": severity,
                "created_at": now,
                "detected_at": datetime.combine(date_key, datetime.min.time()),
                "location_label": "Kenya EEZ Monitoring Box",
                "vessel_name": None,
                "confidence_score": 75.0 if severity != "CRITICAL" else 88.0,
                "risk_score": 40 if severity == "WATCH" else 65 if severity == "ELEVATED" else 85,
                "title": f"{metric_name} {severity.title()} Condition",
                "description": f"{metric_name} is {current:.3f} ({anomaly_pct:+.1f}% vs 30-day mean). Classification: {severity}.",
                "evidence": json.dumps(evidence),
                "status": "OPEN",
                "resolved_at": None
            })

    process_metric(sst_df, "sst_celsius", "SST")
    process_metric(chl_df, "chlorophyll_mg_m3", "CHL")

    # =========================================================
    # 2. PORT INTELLIGENCE (Mombasa)
    # =========================================================
    port_df = con.execute("""
        SELECT *
        FROM pg.public.port_activity
        WHERE event_time >= current_timestamp - INTERVAL '30 days'
    """).fetchdf()

    if not port_df.empty:
        port_df["event_time"] = pd.to_datetime(port_df["event_time"])
        last_24h = port_df[port_df["event_time"] >= now - timedelta(hours=24)]
        last_7d = port_df[port_df["event_time"] >= now - timedelta(days=7)]
        last_30d = port_df

        arrivals_7d = len(last_7d[last_7d["event_type"] == "ARRIVAL"])
        departures_7d = len(last_7d[last_7d["event_type"] == "DEPARTURE"])
        active = len(port_df[port_df["status"] == "IN_PORT"])
        containers = len(last_7d[last_7d["vessel_type"] == "CONTAINER"])
        tankers = len(last_7d[last_7d["vessel_type"] == "TANKER"])
        fishing = len(last_7d[last_7d["vessel_type"] == "FISHING"])

        # Simple congestion proxy
        daily_avg_30d = len(last_30d) / 30
        daily_avg_7d = len(last_7d) / 7 if len(last_7d) else 0
        baseline_pct = ((daily_avg_7d - daily_avg_30d) / daily_avg_30d * 100) if daily_avg_30d else 0
        congestion_index = min(100, max(0, 40 + baseline_pct))

        if congestion_index >= 70:
            congestion_level = "HIGH"
        elif congestion_index >= 45:
            congestion_level = "MODERATE"
        else:
            congestion_level = "LOW"

        avg_waiting = round(random.uniform(3.5, 9.5), 1)  # placeholder until real AIS dwell exists

        port_metrics.append({
            "metric_date": now.date(),
            "port_name": "Mombasa",
            "arrivals": arrivals_7d,
            "departures": departures_7d,
            "active_vessels": active,
            "container_vessels": containers,
            "tankers": tankers,
            "fishing_vessels": fishing,
            "avg_waiting_hours": avg_waiting,
            "congestion_index": round(congestion_index, 1),
            "congestion_level": congestion_level,
            "vs_30d_baseline_pct": round(baseline_pct, 1),
            "created_at": now
        })

        if congestion_level in ("MODERATE", "HIGH"):
            evidence = {
                "congestion_index": round(congestion_index, 1),
                "vs_30d_baseline_pct": round(baseline_pct, 1),
                "arrivals_7d": arrivals_7d,
                "active_vessels": active
            }
            alerts.append({
                "alert_id": random.randint(100000, 999999),
                "alert_type": "PORT_CONGESTION",
                "category": "PORT",
                "severity": "ELEVATED" if congestion_level == "HIGH" else "WATCH",
                "created_at": now,
                "detected_at": now,
                "location_label": "Mombasa Port",
                "vessel_name": None,
                "confidence_score": 70.0,
                "risk_score": 55 if congestion_level == "MODERATE" else 75,
                "title": f"Mombasa Port Congestion {congestion_level}",
                "description": f"Congestion index {congestion_index:.1f}. Activity {baseline_pct:+.1f}% vs 30-day baseline.",
                "evidence": json.dumps(evidence),
                "status": "OPEN",
                "resolved_at": None
            })

    # =========================================================
    # 3. FISHING RISK (sample behaviour scoring)
    # =========================================================
    fish_df = con.execute("""
        SELECT *
        FROM pg.public.fishing_activity
        WHERE event_time >= current_timestamp - INTERVAL '7 days'
    """).fetchdf()

    if not fish_df.empty:
        # Score a subset of high-effort events as potential risk
        high = fish_df[fish_df["apparent_effort"] == "HIGH"].head(8)
        for _, row in high.iterrows():
            risk_score = round(random.uniform(62, 88), 1)
            confidence = round(random.uniform(55, 80), 1)
            evidence_list = [
                "Extended low-speed / high-effort activity",
                "Activity inside Kenya EEZ monitoring box"
            ]
            if row["longitude"] > 40.5 and row["longitude"] < 41.5 and row["latitude"] > -3 and row["latitude"] < -2:
                evidence_list.append("Activity near sample MPA boundary")
                risk_score = min(95, risk_score + 8)

            evidence_list.append(f"Vessel type: {row['vessel_type']}")
            evidence_list.append(f"Reported effort: {row['apparent_effort']}")

            fishing_risks.append({
                "risk_id": random.randint(10000, 99999),
                "event_time": row["event_time"],
                "vessel_name": row["vessel_name"],
                "vessel_type": row["vessel_type"],
                "flag_country": row["flag_country"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "risk_score": risk_score,
                "confidence_score": confidence,
                "evidence": " | ".join(evidence_list),
                "status": "REQUIRES_HUMAN_REVIEW",
                "created_at": now
            })

            if risk_score >= 75:
                alerts.append({
                    "alert_id": random.randint(100000, 999999),
                    "alert_type": "FISHING_RISK",
                    "category": "FISHING",
                    "severity": "ELEVATED",
                    "created_at": now,
                    "detected_at": row["event_time"],
                    "location_label": f"{row['latitude']:.3f}, {row['longitude']:.3f}",
                    "vessel_name": row["vessel_name"],
                    "confidence_score": confidence,
                    "risk_score": risk_score,
                    "title": "Potential Anomalous Fishing Activity",
                    "description": f"Risk score {risk_score}/100. Status: Requires human review. Not classified as illegal.",
                    "evidence": " | ".join(evidence_list),
                    "status": "OPEN",
                    "resolved_at": None
                })

    # =========================================================
    # 4. SYSTEM HEARTBEAT
    # =========================================================
    alerts.append({
        "alert_id": random.randint(100000, 999999),
        "alert_type": "SYSTEM",
        "category": "SYSTEM",
        "severity": "INFO",
        "created_at": now,
        "detected_at": now,
        "location_label": "OceanWatch Platform",
        "vessel_name": None,
        "confidence_score": 100.0,
        "risk_score": 0,
        "title": "OceanWatch Monitoring Active",
        "description": "Operational intelligence engine completed successfully.",
        "evidence": json.dumps({"modules": ["COASTAL", "PORT", "FISHING"]}),
        "status": "OPEN",
        "resolved_at": None
    })

    # ---------- Write results ----------
    def write_df(table, records):
        if not records:
            return
        df = pd.DataFrame(records)
        con.execute(f"DELETE FROM pg.public.{table} WHERE created_at::date = current_date;")
        con.register("tmp_df", df)
        con.execute(f"INSERT INTO pg.public.{table} SELECT * FROM tmp_df;")
        logger.info(f"Wrote {len(df)} rows → {table}")

    write_df("fact_alerts", alerts)
    write_df("fact_ocean_anomalies", anomalies)
    write_df("fact_port_metrics", port_metrics)
    write_df("fact_fishing_risk", fishing_risks)

    con.close()
    logger.info("=== Operational Intelligence Engine completed ===")


if __name__ == "__main__":
    run_engine()
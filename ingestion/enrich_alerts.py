"""Insert anomaly-driven alerts into fact_alerts (exact schema)."""

import logging
from datetime import datetime
import random

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Alert enrichment ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    anoms = con.execute(
        """
        SELECT metric_name, as_of_date, status, anomaly_pct, explanation,
               current_value, baseline_value
        FROM pg.public.fact_oceanwatch_anomalies
        WHERE status IN ('ELEVATED', 'HIGH', 'CRITICAL')
        """
    ).fetchdf()

    if anoms is None or len(anoms) == 0:
        logger.info("No elevated+ anomalies to alert on")
        logger.info("=== Alert enrichment completed ===")
        return

    now = datetime.utcnow()
    n = 0

    why_map = {
        "SST_CELSIUS": "Sea surface temperature shifts can affect ecosystems and coastal conditions.",
        "CHLOROPHYLL": "Chlorophyll anomalies can signal bloom risk or productivity changes.",
        "PORT_CONGESTION_INDEX": "Congestion changes affect vessel waiting time and port planning.",
        "GFW_FISHING_HOURS": "Fishing-effort shifts matter for fisheries monitoring (not a legal finding).",
    }

    type_map = {
        "SST_CELSIUS": "OCEAN_ANOMALY",
        "CHLOROPHYLL": "OCEAN_ANOMALY",
        "PORT_CONGESTION_INDEX": "PORT_CONGESTION",
        "GFW_FISHING_HOURS": "FISHING_EFFORT_ANOMALY",
    }

    for _, r in anoms.iterrows():
        metric = str(r["metric_name"])
        status = str(r["status"])
        title = f"{metric} {status}"
        why = why_map.get(
            metric,
            "Unusual change vs recent baseline — operational awareness only.",
        )
        cat = "OCEAN"
        if "PORT" in metric:
            cat = "PORT"
        elif "GFW" in metric or "FISH" in metric:
            cat = "FISHING"

        alert_type = type_map.get(metric, "ANOMALY")
        conf = 70.0 if status == "ELEVATED" else 85.0 if status == "HIGH" else 90.0
        risk = abs(float(r["anomaly_pct"] or 0))
        desc = str(r["explanation"])
        evidence = (
            f"current={r['current_value']}; baseline={r['baseline_value']}; "
            f"pct={r['anomaly_pct']}; as_of={r['as_of_date']}"
        )
        alert_id = random.randint(1_000_000, 9_999_999)

        con.execute(
            "DELETE FROM pg.public.fact_alerts WHERE title = ? AND alert_type = ?",
            [title, alert_type],
        )

        con.execute(
            """
            INSERT INTO pg.public.fact_alerts (
                alert_id,
                alert_type,
                category,
                severity,
                created_at,
                detected_at,
                location_label,
                vessel_name,
                confidence_score,
                risk_score,
                title,
                description,
                evidence,
                status,
                resolved_at,
                why_it_matters,
                data_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, 'OPEN', NULL, ?, ?)
            """,
            [
                alert_id,
                alert_type,
                cat,
                status,
                now,
                now,
                "Kenya EEZ monitoring box",
                conf,
                risk,
                title,
                desc,
                evidence,
                why,
                "OceanWatch anomaly engine",
            ],
        )
        n += 1
        logger.info("Inserted %s", title)

    logger.info("Inserted %s anomaly-based alerts", n)
    logger.info("=== Alert enrichment completed ===")


if __name__ == "__main__":
    main()
"""
OceanWatch Anomaly Engine — baselines vs recent values.
Writes fact_oceanwatch_anomalies for dashboard use.
"""

import logging
from datetime import datetime

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def classify(pct: float | None, abs_thresh=(10, 25, 40)):
    if pct is None:
        return "UNKNOWN", 0.0
    a = abs(pct)
    if a < abs_thresh[0]:
        return "NORMAL", a
    if a < abs_thresh[1]:
        return "ELEVATED", a
    if a < abs_thresh[2]:
        return "HIGH", a
    return "CRITICAL", a


def main():
    logger.info("=== OceanWatch Anomaly Engine ===")
    uri = get_db_uri()
    con = duckdb.connect()
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_oceanwatch_anomalies (
            anomaly_id VARCHAR PRIMARY KEY,
            metric_name VARCHAR,
            as_of_date DATE,
            current_value DOUBLE,
            baseline_value DOUBLE,
            anomaly_value DOUBLE,
            anomaly_pct DOUBLE,
            status VARCHAR,
            window_days INTEGER,
            explanation VARCHAR,
            created_at TIMESTAMP
        )
        """
    )

    rows = []

    # SST: latest vs prior 14-day mean (excluding latest)
    sst = con.execute(
        """
        SELECT date_key::DATE AS d, sst_celsius::DOUBLE AS v
        FROM pg.public.fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
        """
    ).fetchdf()

    if len(sst) >= 5:
        cur = float(sst.iloc[-1]["v"])
        d = sst.iloc[-1]["d"]
        base = float(sst.iloc[:-1].tail(14)["v"].mean())
        delta = cur - base
        pct = (delta / base * 100.0) if base else None
        status, _ = classify(pct, (0.5, 1.5, 3.0))  # °C-ish via pct of baseline
        # Prefer absolute °C thresholds for SST
        if abs(delta) < 0.3:
            status = "NORMAL"
        elif abs(delta) < 0.8:
            status = "ELEVATED"
        elif abs(delta) < 1.5:
            status = "HIGH"
        else:
            status = "CRITICAL"
        rows.append(
            (
                f"sst_{d}",
                "SST_CELSIUS",
                d,
                cur,
                base,
                delta,
                pct,
                status,
                14,
                f"SST {cur:.2f}°C vs ~14d baseline {base:.2f}°C (Δ {delta:+.2f}°C).",
            )
        )

    # CHL
    chl = con.execute(
        """
        SELECT date_key::DATE AS d, chlorophyll_mg_m3::DOUBLE AS v
        FROM pg.public.fact_ocean_conditions
        WHERE chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key
        """
    ).fetchdf()

    if len(chl) >= 5:
        cur = float(chl.iloc[-1]["v"])
        d = chl.iloc[-1]["d"]
        base = float(chl.iloc[:-1].tail(14)["v"].mean())
        delta = cur - base
        pct = (delta / base * 100.0) if base else None
        status, _ = classify(pct, (15, 30, 50))
        rows.append(
            (
                f"chl_{d}",
                "CHLOROPHYLL",
                d,
                cur,
                base,
                delta,
                pct,
                status,
                14,
                f"CHL {cur:.3f} vs baseline {base:.3f} ({pct:+.1f}% ).",
            )
        )

    # Port congestion index
    try:
        port = con.execute(
            """
            SELECT metric_date::DATE AS d, congestion_index::DOUBLE AS v,
                   active_vessels::DOUBLE AS av
            FROM pg.public.fact_port_metrics
            ORDER BY metric_date
            """
        ).fetchdf()
        if len(port) >= 1:
            cur = float(port.iloc[-1]["v"])
            d = port.iloc[-1]["d"]
            base = float(port["v"].mean()) if len(port) > 1 else cur
            delta = cur - base
            pct = (delta / base * 100.0) if base else 0.0
            status, _ = classify(pct, (10, 25, 50))
            rows.append(
                (
                    f"port_cong_{d}",
                    "PORT_CONGESTION_INDEX",
                    d,
                    cur,
                    base,
                    delta,
                    pct,
                    status,
                    max(len(port), 1),
                    f"Congestion index {cur:.0f} vs series mean {base:.0f} ({pct:+.1f}%).",
                )
            )
    except Exception as e:
        logger.warning("Port anomaly skipped: %s", e)

    # GFW total hours last day vs mean day
    try:
        # discover hours column via SELECT *
        gfw = con.execute(
            """
            SELECT * FROM pg.public.fact_gfw_fishing_effort LIMIT 5000
            """
        ).fetchdf()
        if not gfw.empty:
            hour_col = next((c for c in gfw.columns if "hour" in c.lower()), None)
            date_col = next(
                (c for c in gfw.columns if "date" in c.lower() or c.lower() == "day"),
                None,
            )
            if hour_col and date_col:
                gfw[date_col] = gfw[date_col].astype(str)
                daily = gfw.groupby(date_col)[hour_col].sum().sort_index()
                if len(daily) >= 2:
                    cur = float(daily.iloc[-1])
                    d = daily.index[-1]
                    base = float(daily.iloc[:-1].mean())
                    delta = cur - base
                    pct = (delta / base * 100.0) if base else None
                    status, _ = classify(pct, (20, 40, 70))
                    rows.append(
                        (
                            f"gfw_{d}",
                            "GFW_FISHING_HOURS",
                            d,
                            cur,
                            base,
                            delta,
                            pct,
                            status,
                            len(daily),
                            f"GFW hours {cur:.1f} vs prior days mean {base:.1f} ({pct:+.1f}%).",
                        )
                    )
    except Exception as e:
        logger.warning("GFW anomaly skipped: %s", e)

    now = datetime.utcnow()
    con.execute("DELETE FROM pg.public.fact_oceanwatch_anomalies")
    for r in rows:
        con.execute(
            """
            INSERT INTO pg.public.fact_oceanwatch_anomalies
            (anomaly_id, metric_name, as_of_date, current_value, baseline_value,
             anomaly_value, anomaly_pct, status, window_days, explanation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [*r, now],
        )
        logger.info("%s %s status=%s", r[1], r[8] if False else r[0], r[7])

    logger.info("Wrote %s anomaly rows", len(rows))
    logger.info("=== Anomaly Engine completed ===")


if __name__ == "__main__":
    main()
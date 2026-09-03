"""
Phase 14 complete — Port Intelligence (Mombasa).
Performance, congestion forecast, arrival forecast, berth pressure, ops risk.
"""

import logging
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase14_port_v1.0"
PORT = "Mombasa"
# Assumed operational capacity proxy for berth pressure (demo)
CAPACITY_PROXY = 45


def get_db_uri():
    import os
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def connect():
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
    return con


def cols(con, table):
    try:
        return [
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM pg.information_schema.columns
                WHERE table_schema='public' AND table_name=?
                """,
                [table],
            ).fetchall()
        ]
    except Exception:
        return []


def write(con, table, df):
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No columns for %s", table)
        return
    con.execute(f"DELETE FROM pg.public.{table}")
    con.register("_t", df[use])
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _t"
    )
    logger.info("%s: %s rows", table, len(df))


def qdf(con, sql):
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def level_from_index(idx):
    if idx >= 80:
        return "HIGH"
    if idx >= 55:
        return "MODERATE"
    if idx >= 30:
        return "LOW"
    return "CLEAR"


def build_performance(metrics: pd.DataFrame, now):
    if metrics.empty:
        return pd.DataFrame()
    rows = []
    for _, m in metrics.iterrows():
        arr = int(m.get("arrivals") or 0)
        dep = int(m.get("departures") or 0)
        active = int(m.get("active_vessels") or 0)
        idx = float(m.get("congestion_index") or 0)
        level = str(m.get("congestion_level") or level_from_index(idx))
        wait = float(m.get("avg_waiting_hours") or 0)
        baseline = float(m.get("vs_30d_baseline_pct") or 0)
        throughput = float(arr + dep)
        balance = float(arr / dep) if dep else float(arr)
        # Performance: high throughput, moderate congestion, lower wait is better
        perf = 100.0
        perf -= min(40.0, idx * 0.35)
        perf -= min(25.0, wait * 2.0)
        perf += min(15.0, throughput * 0.3)
        perf = max(0.0, min(100.0, perf))
        rows.append(
            dict(
                metric_date=m.get("metric_date"),
                port_name=str(m.get("port_name") or PORT),
                arrivals=arr,
                departures=dep,
                active_vessels=active,
                container_vessels=int(m.get("container_vessels") or 0),
                tankers=int(m.get("tankers") or 0),
                fishing_vessels=int(m.get("fishing_vessels") or 0),
                avg_waiting_hours=wait,
                congestion_index=idx,
                congestion_level=level,
                vs_30d_baseline_pct=baseline,
                throughput_proxy=throughput,
                balance_ratio=round(balance, 3),
                performance_score=round(perf, 1),
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_congestion_forecast(metrics: pd.DataFrame, now, horizon=7):
    if metrics.empty:
        return pd.DataFrame()
    m = metrics.sort_values("metric_date")
    series = m["congestion_index"].astype(float).tolist()
    if not series:
        return pd.DataFrame()
    # Persistence + small mean-reversion toward rolling mean
    last = series[-1]
    mean = float(np.mean(series[-min(14, len(series)) :]))
    mae = float(np.mean(np.abs(np.diff(series)))) if len(series) > 1 else 5.0
    rows = []
    pred = last
    for h in range(1, horizon + 1):
        pred = 0.7 * pred + 0.3 * mean
        pred = max(0.0, min(100.0, pred))
        rows.append(
            dict(
                forecast_date=(now.date() + timedelta(days=h)),
                horizon_day=h,
                port_name=PORT,
                predicted_congestion_index=round(pred, 1),
                predicted_level=level_from_index(pred),
                lower_bound=round(max(0.0, pred - mae), 1),
                upper_bound=round(min(100.0, pred + mae), 1),
                model_name="persistence_mean_revert",
                mae=round(mae, 2),
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_arrival_forecast(metrics: pd.DataFrame, now, horizon=7):
    if metrics.empty:
        return pd.DataFrame()
    m = metrics.sort_values("metric_date")
    arr = m["arrivals"].astype(float).tolist()
    dep = m["departures"].astype(float).tolist()
    arr_mean = float(np.mean(arr[-min(14, len(arr)) :])) if arr else 0.0
    dep_mean = float(np.mean(dep[-min(14, len(dep)) :])) if dep else 0.0
    last_arr = arr[-1] if arr else arr_mean
    last_dep = dep[-1] if dep else dep_mean
    rows = []
    for h in range(1, horizon + 1):
        pa = 0.6 * last_arr + 0.4 * arr_mean
        pd_ = 0.6 * last_dep + 0.4 * dep_mean
        last_arr, last_dep = pa, pd_
        rows.append(
            dict(
                forecast_date=(now.date() + timedelta(days=h)),
                horizon_day=h,
                port_name=PORT,
                predicted_arrivals=round(pa, 1),
                predicted_departures=round(pd_, 1),
                model_name="ewma_baseline",
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_berth_pressure(latest: dict, now):
    active = int(latest.get("active_vessels") or 0)
    util = (active / CAPACITY_PROXY) * 100.0 if CAPACITY_PROXY else 0.0
    score = min(100.0, util)
    if util >= 100:
        level = "CRITICAL"
    elif util >= 80:
        level = "HIGH"
    elif util >= 60:
        level = "MODERATE"
    else:
        level = "LOW"
    drivers = f"active={active} capacity_proxy={CAPACITY_PROXY} util={util:.1f}%"
    return pd.DataFrame(
        [
            dict(
                as_of_date=latest.get("metric_date") or now.date(),
                port_name=PORT,
                active_vessels=active,
                capacity_proxy=CAPACITY_PROXY,
                berth_utilization_pct=round(util, 1),
                pressure_score=round(score, 1),
                pressure_level=level,
                drivers=drivers,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def build_ops_risk(con, latest: dict, berth: pd.DataFrame, now):
    idx = float(latest.get("congestion_index") or 0)
    wait = float(latest.get("avg_waiting_hours") or 0)
    baseline = float(latest.get("vs_30d_baseline_pct") or 0)
    traffic = min(100.0, 20 + float(latest.get("active_vessels") or 0) * 1.5)
    congestion = idx
    berth_score = float(berth.iloc[0]["pressure_score"]) if not berth.empty else 40.0

    # Tide score from fact_port_risk if present
    tide_score = 30.0
    pr = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_risk
        ORDER BY risk_date DESC LIMIT 1
        """,
    )
    drivers = [f"congestion_index={idx}", f"wait={wait}h", f"baseline={baseline}%"]
    if not pr.empty:
        p = pr.iloc[0]
        if pd.notna(p.get("tide_score")):
            tide_score = float(p["tide_score"])
            drivers.append(f"tide_score={tide_score}")
        if pd.notna(p.get("composite_risk")):
            drivers.append(f"prior_composite={p.get('composite_risk')}")

    composite = (
        0.35 * congestion
        + 0.25 * traffic
        + 0.25 * berth_score
        + 0.15 * min(100.0, tide_score)
    )
    composite = float(min(100.0, max(0.0, composite)))
    if composite >= 75:
        level = "HIGH"
    elif composite >= 55:
        level = "ELEVATED"
    elif composite >= 35:
        level = "WATCH"
    else:
        level = "LOW"

    return pd.DataFrame(
        [
            dict(
                as_of_date=latest.get("metric_date") or now.date(),
                port_name=PORT,
                traffic_score=round(traffic, 1),
                congestion_score=round(congestion, 1),
                tide_score=round(tide_score, 1),
                berth_score=round(berth_score, 1),
                composite_ops_risk=round(composite, 1),
                risk_level=level,
                confidence_score=78.0,
                drivers=" | ".join(drivers),
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def run():
    logger.info("=== Phase 14 port intelligence ===")
    now = datetime.utcnow()
    con = connect()

    metrics = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_metrics
        ORDER BY metric_date
        """,
    )
    logger.info("Port metric rows: %s", len(metrics))
    if metrics.empty:
        logger.warning("No fact_port_metrics — seed_port_activity first")
        return

    # Normalize date
    metrics["metric_date"] = pd.to_datetime(metrics["metric_date"]).dt.date

    perf = build_performance(metrics, now)
    write(con, "fact_port_performance", perf)

    cong_fc = build_congestion_forecast(metrics, now)
    write(con, "fact_port_congestion_forecast", cong_fc)

    arr_fc = build_arrival_forecast(metrics, now)
    write(con, "fact_port_arrival_forecast", arr_fc)

    latest = metrics.sort_values("metric_date").iloc[-1].to_dict()
    berth = build_berth_pressure(latest, now)
    write(con, "fact_berth_pressure", berth)

    ops = build_ops_risk(con, latest, berth, now)
    write(con, "fact_port_ops_risk", ops)

    logger.info(
        "Perf rows=%s cong_fc=%s arr_fc=%s berth=%s ops=%s",
        len(perf),
        len(cong_fc),
        len(arr_fc),
        len(berth),
        len(ops),
    )
    if not ops.empty:
        o = ops.iloc[0]
        logger.info(
            "Ops risk=%s %s | %s",
            o.get("composite_ops_risk"),
            o.get("risk_level"),
            o.get("drivers"),
        )
    logger.info("=== Phase 14 complete ===")


if __name__ == "__main__":
    run()
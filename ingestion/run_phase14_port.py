"""
Phase 14 — Port Intelligence (Mombasa).

Performance, congestion forecast, arrival forecast, berth pressure, ops risk.
Uses ingestion/.env OCEANWATCH_DB_URI via db_utils (not localhost hardcode).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_utils import attach_postgres, qdf, write_df  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase14_port_v1.0"
PORT = "Mombasa"
CAPACITY_PROXY = 45


def level_from_index(idx: float) -> str:
    if idx >= 80:
        return "HIGH"
    if idx >= 55:
        return "MODERATE"
    if idx >= 30:
        return "LOW"
    return "CLEAR"


def build_performance(metrics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    rows = []
    for _, m in metrics.iterrows():
        arr = int(m.get("arrivals") or m.get("arrival_count") or 0)
        dep = int(m.get("departures") or m.get("departure_count") or 0)
        active = int(m.get("active_vessels") or m.get("vessel_count") or 0)
        idx = float(m.get("congestion_index") or 0)
        level = str(m.get("congestion_level") or level_from_index(idx))
        wait = float(m.get("avg_waiting_hours") or 0)
        baseline = float(m.get("vs_30d_baseline_pct") or 0)
        throughput = float(arr + dep)
        balance = float(arr / dep) if dep else float(arr)
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


def build_congestion_forecast(metrics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    s = metrics.sort_values("metric_date")
    y = pd.to_numeric(s["congestion_index"], errors="coerce").fillna(40.0).values
    if len(y) < 3:
        base = float(y[-1]) if len(y) else 40.0
        trend = 0.0
    else:
        base = float(np.mean(y[-7:]))
        trend = float(y[-1] - y[-8]) / 7.0 if len(y) >= 8 else float(y[-1] - y[0]) / max(1, len(y) - 1)
    last_date = pd.to_datetime(s["metric_date"].iloc[-1]).date()
    rows = []
    for h in range(1, 8):
        pred = max(0.0, min(100.0, base + trend * h + float(np.sin(h / 2.0) * 3)))
        band = 8.0 + h * 1.5
        rows.append(
            dict(
                forecast_date=last_date + timedelta(days=h),
                horizon_day=h,
                port_name=PORT,
                congestion_index_pred=round(pred, 2),
                congestion_level=level_from_index(pred),
                lo=round(max(0.0, pred - band), 2),
                hi=round(min(100.0, pred + band), 2),
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_arrival_forecast(metrics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()
    s = metrics.sort_values("metric_date")
    arr_col = "arrivals" if "arrivals" in s.columns else "arrival_count"
    y = pd.to_numeric(s[arr_col], errors="coerce").fillna(5.0).values
    base = float(np.mean(y[-7:])) if len(y) else 5.0
    last_date = pd.to_datetime(s["metric_date"].iloc[-1]).date()
    rows = []
    for h in range(1, 8):
        pred = max(0.0, base + float(np.sin(h / 1.7) * 1.5))
        rows.append(
            dict(
                forecast_date=last_date + timedelta(days=h),
                horizon_day=h,
                port_name=PORT,
                arrivals_pred=round(pred, 2),
                lo=round(max(0.0, pred - 2.5 - h * 0.2), 2),
                hi=round(pred + 2.5 + h * 0.2, 2),
                model_version=MODEL,
                created_at=now,
            )
        )
    return pd.DataFrame(rows)


def build_berth_pressure(latest: dict, now: datetime) -> pd.DataFrame:
    active = int(latest.get("active_vessels") or latest.get("vessel_count") or 0)
    arr = int(latest.get("arrivals") or latest.get("arrival_count") or 0)
    dep = int(latest.get("departures") or latest.get("departure_count") or 0)
    wait = float(latest.get("avg_waiting_hours") or 0)
    occ = min(150.0, 100.0 * active / max(1, CAPACITY_PROXY))
    pressure = min(100.0, occ * 0.7 + min(30.0, wait * 3) + min(20.0, max(0, arr - dep) * 4))
    if pressure >= 75:
        level = "CRITICAL"
    elif pressure >= 55:
        level = "HIGH"
    elif pressure >= 35:
        level = "MODERATE"
    else:
        level = "LOW"
    return pd.DataFrame(
        [
            dict(
                as_of=now,
                port_name=PORT,
                active_vessels=active,
                capacity_proxy=CAPACITY_PROXY,
                occupancy_pct=round(occ, 1),
                pressure_index=round(pressure, 1),
                pressure_level=level,
                arrivals_today=arr,
                departures_today=dep,
                waiting_hours=wait,
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def build_ops_risk(con, latest: dict, berth: pd.DataFrame, now: datetime) -> pd.DataFrame:
    cong = float(latest.get("congestion_index") or 0)
    wait = float(latest.get("avg_waiting_hours") or 0)
    arr = float(latest.get("arrivals") or latest.get("arrival_count") or 0)
    dep = float(latest.get("departures") or latest.get("departure_count") or 0)
    berth_p = float(berth.iloc[0]["pressure_index"]) if not berth.empty else 40.0

    # Optional vessel anomaly pressure near Mombasa
    anomaly_c = 0.0
    try:
        adf = qdf(
            con,
            """
            SELECT COUNT(*) AS n
            FROM pg.public.fact_vessel_anomalies
            WHERE detected_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
            """,
        )
        if not adf.empty:
            anomaly_c = min(40.0, float(adf.iloc[0]["n"]) * 4.0)
    except Exception:  # noqa: BLE001
        pass
    # behaviour / profiles near port
    try:
        pdf = qdf(
            con,
            """
            SELECT AVG(COALESCE(risk_score, behaviour_score, 0)) AS avg_r
            FROM pg.public.fact_vessel_profiles
            WHERE COALESCE(near_mombasa, near_port, FALSE) = TRUE
            """,
        )
        if not pdf.empty and pd.notna(pdf.iloc[0]["avg_r"]):
            anomaly_c = max(anomaly_c, min(40.0, float(pdf.iloc[0]["avg_r"]) * 0.4))
    except Exception:  # noqa: BLE001
        pass

    balance_imbalance = abs(arr - dep)
    balance_c = min(25.0, balance_imbalance * 3.0)
    wait_c = min(30.0, wait * 4.0)
    cong_c = min(40.0, cong * 0.4)
    berth_c = min(40.0, berth_p * 0.4)

    composite = min(
        100.0,
        cong_c * 0.3 + berth_c * 0.25 + wait_c * 0.2 + balance_c * 0.1 + anomaly_c * 0.15,
    )
    if composite >= 70:
        level = "HIGH"
    elif composite >= 45:
        level = "MODERATE"
    elif composite >= 25:
        level = "LOW"
    else:
        level = "CLEAR"

    drivers = []
    if cong_c >= 15:
        drivers.append(f"congestion={cong:.0f}")
    if berth_c >= 15:
        drivers.append(f"berth_pressure={berth_p:.0f}")
    if wait_c >= 10:
        drivers.append(f"wait_h={wait:.1f}")
    if balance_c >= 8:
        drivers.append(f"arr-dep_gap={balance_imbalance:.0f}")
    if anomaly_c >= 10:
        drivers.append(f"vessel_risk={anomaly_c:.0f}")
    if not drivers:
        drivers.append("nominal_ops")

    return pd.DataFrame(
        [
            dict(
                as_of=now,
                port_name=PORT,
                congestion_component=round(cong_c, 1),
                berth_component=round(berth_c, 1),
                wait_component=round(wait_c, 1),
                balance_component=round(balance_c, 1),
                anomaly_component=round(anomaly_c, 1),
                composite_ops_risk=round(composite, 1),
                risk_level=level,
                drivers=" | ".join(drivers),
                model_version=MODEL,
                created_at=now,
            )
        ]
    )


def _ensure_metrics(con) -> pd.DataFrame:
    metrics = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_metrics
        ORDER BY metric_date
        """,
    )
    if not metrics.empty:
        return metrics
    logger.warning("No fact_port_metrics — running seed_port_activity")
    try:
        import seed_port_activity as spa

        spa.seed_port_activity()
    except Exception as exc:  # noqa: BLE001
        logger.error("seed_port_activity failed: %s", exc)
        return pd.DataFrame()
    return qdf(
        con,
        """
        SELECT * FROM pg.public.fact_port_metrics
        ORDER BY metric_date
        """,
    )


def run() -> dict:
    logger.info("=== Phase 14 port intelligence ===")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Schema first
    try:
        from init_phase14_port import main as ensure_schema

        ensure_schema()
    except Exception as exc:  # noqa: BLE001
        logger.warning("schema ensure: %s", exc)

    con = attach_postgres()
    summary: dict = {}

    metrics = _ensure_metrics(con)
    logger.info("Port metric rows: %s", len(metrics))
    summary["metrics"] = len(metrics)
    if metrics.empty:
        logger.error("No fact_port_metrics after seed — abort")
        summary["status"] = "empty_metrics"
        return summary

    # Normalize column names from seed variants
    rename = {}
    if "arrival_count" in metrics.columns and "arrivals" not in metrics.columns:
        rename["arrival_count"] = "arrivals"
    if "departure_count" in metrics.columns and "departures" not in metrics.columns:
        rename["departure_count"] = "departures"
    if "vessel_count" in metrics.columns and "active_vessels" not in metrics.columns:
        rename["vessel_count"] = "active_vessels"
    if rename:
        metrics = metrics.rename(columns=rename)

    metrics["metric_date"] = pd.to_datetime(metrics["metric_date"]).dt.date

    perf = build_performance(metrics, now)
    write_df(con, "fact_port_performance", perf, replace=True)
    summary["performance"] = len(perf)

    cong_fc = build_congestion_forecast(metrics, now)
    write_df(con, "fact_port_congestion_forecast", cong_fc, replace=True)
    summary["congestion_fc"] = len(cong_fc)

    arr_fc = build_arrival_forecast(metrics, now)
    write_df(con, "fact_port_arrival_forecast", arr_fc, replace=True)
    summary["arrival_fc"] = len(arr_fc)

    latest = metrics.sort_values("metric_date").iloc[-1].to_dict()
    berth = build_berth_pressure(latest, now)
    write_df(con, "fact_berth_pressure", berth, replace=True)
    summary["berth"] = len(berth)

    ops = build_ops_risk(con, latest, berth, now)
    write_df(con, "fact_port_ops_risk", ops, replace=True)
    summary["ops_risk"] = len(ops)

    if not ops.empty:
        o = ops.iloc[0]
        logger.info(
            "Ops risk=%s %s | %s",
            o.get("composite_ops_risk"),
            o.get("risk_level"),
            o.get("drivers"),
        )
    summary["status"] = "ok"
    logger.info("=== Phase 14 complete === %s", summary)
    return summary


if __name__ == "__main__":
    run()

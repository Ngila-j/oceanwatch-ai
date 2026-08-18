import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

st.set_page_config(page_title="Operational Alerts", page_icon="🚨", layout="wide")
st.title("🚨 Operational Alerts")
st.caption("Central OceanWatch alert surface — port, fishing, coastal, and system signals")


@st.cache_resource
def get_engine():
    return create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")


@st.cache_data(ttl=120)
def load_alerts():
    engine = get_engine()
    try:
        return pd.read_sql(
            """
            SELECT *
            FROM fact_alerts
            ORDER BY created_at DESC
            LIMIT 200
            """,
            engine,
        )
    except Exception:
        try:
            return pd.read_sql(
                """
                SELECT *
                FROM operational_alerts
                ORDER BY created_at DESC
                LIMIT 200
                """,
                engine,
            )
        except Exception as e:
            st.warning(f"Alert tables not available: {e}")
            return pd.DataFrame()


@st.cache_data(ttl=180)
def load_gfw_summary():
    engine = get_engine()
    try:
        row = pd.read_sql(
            """
            SELECT
                COUNT(*) AS cells,
                COALESCE(SUM(hours), 0) AS total_hours,
                COUNT(DISTINCT effort_date) AS days
            FROM fact_gfw_fishing_effort
            """,
            engine,
        )
        if row.empty:
            return None
        return {
            "cells": int(row.iloc[0]["cells"]),
            "total_hours": float(row.iloc[0]["total_hours"]),
            "days": int(row.iloc[0]["days"]),
        }
    except Exception:
        return None


@st.cache_data(ttl=180)
def load_port_metrics():
    engine = get_engine()
    try:
        return pd.read_sql(
            """
            SELECT *
            FROM fact_port_metrics
            ORDER BY metric_date DESC
            LIMIT 1
            """,
            engine,
        )
    except Exception:
        return pd.DataFrame()


# --- GFW context strip ---
gfw_sum = load_gfw_summary()
if gfw_sum is not None:
    a, b, c = st.columns(3)
    a.metric("GFW effort cells (region)", gfw_sum["cells"])
    b.metric("GFW fishing hours", f"{gfw_sum['total_hours']:.1f}")
    c.metric("GFW days covered", gfw_sum["days"])
    st.caption(
        "GFW context · powered by [Global Fishing Watch](https://globalfishingwatch.org) · "
        "see **GFW Fishing Effort** page for spatial detail"
    )
else:
    st.info("GFW summary not available yet. Run `fetch_gfw_fishing_effort.py` to populate.")

st.markdown("---")

# --- Port snapshot ---
port = load_port_metrics()
if not port.empty:
    row = port.iloc[0]
    st.subheader("Mombasa port snapshot")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Active vessels", int(row.get("active_vessels") or 0))
    p2.metric("Arrivals", int(row.get("arrivals") or 0))
    p3.metric("Congestion", str(row.get("congestion_level") or "n/a"))
    p4.metric("vs 30d baseline", f"{float(row.get('vs_30d_baseline_pct') or 0):.1f}%")

# --- Alerts table ---
st.subheader("Active / recent alerts")
alerts = load_alerts()

if alerts.empty:
    st.success("No alerts in the database right now.")
else:
    severity_col = "severity" if "severity" in alerts.columns else None
    category_col = "category" if "category" in alerts.columns else (
        "alert_type" if "alert_type" in alerts.columns else None
    )

    filters = st.columns(3)
    with filters[0]:
        if severity_col:
            sev_opts = ["All"] + sorted(alerts[severity_col].dropna().astype(str).unique().tolist())
            sev = st.selectbox("Severity", sev_opts)
        else:
            sev = "All"
    with filters[1]:
        if category_col:
            cat_opts = ["All"] + sorted(alerts[category_col].dropna().astype(str).unique().tolist())
            cat = st.selectbox("Category", cat_opts)
        else:
            cat = "All"
    with filters[2]:
        limit = st.slider("Rows", 10, 200, 50)

    view = alerts.copy()
    if sev != "All" and severity_col:
        view = view[view[severity_col].astype(str) == sev]
    if cat != "All" and category_col:
        view = view[view[category_col].astype(str) == cat]

    k1, k2, k3 = st.columns(3)
    k1.metric("Alerts shown", len(view.head(limit)))
    if severity_col:
        elevated = view[
            view[severity_col].astype(str).str.upper().isin(
                ["HIGH", "ELEVATED", "CRITICAL", "WARNING"]
            )
        ]
        k2.metric("Elevated / high", len(elevated))
    else:
        k2.metric("Elevated / high", "—")
    k3.metric("Last refresh", datetime.utcnow().strftime("%H:%M UTC"))

    preferred = [
        c
        for c in [
            "created_at",
            "alert_date",
            "category",
            "alert_type",
            "severity",
            "title",
            "message",
            "risk_score",
            "status",
        ]
        if c in view.columns
    ]
    st.dataframe(
        view[preferred].head(limit) if preferred else view.head(limit),
        use_container_width=True,
    )

st.markdown("---")
st.page_link("pages/15_GFW_Fishing_Effort.py", label="Open GFW Fishing Effort →")
st.page_link("pages/9_Fishing_Activity.py", label="Open Fishing Activity →")
st.page_link("pages/8_Port_Intelligence.py", label="Open Port Intelligence →")

st.caption(
    "Alerts are decision-support signals only. "
    "GFW apparent fishing effort is model-derived from AIS and is not a legal determination of fishing activity."
)
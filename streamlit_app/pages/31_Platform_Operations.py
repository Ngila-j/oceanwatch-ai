"""Phase 16 — Platform operations dashboard."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Platform Operations",
    page_icon=":material/dns:",
    layout="wide",
)
st.title("Platform Operations")
st.caption("System reliability · report runs · alert delivery dry-run · API surface")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=30)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "health": q(
            "SELECT * FROM fact_system_health ORDER BY check_time DESC, component"
        ),
        "reports": q(
            "SELECT * FROM fact_report_runs ORDER BY generated_at DESC LIMIT 10"
        ),
        "deliveries": q(
            "SELECT * FROM fact_alert_deliveries ORDER BY attempted_at DESC LIMIT 100"
        ),
        "api": q(
            "SELECT * FROM fact_api_usage_daily ORDER BY usage_date DESC, endpoint"
        ),
        "roles": q("SELECT user_id, role FROM user_roles ORDER BY role, user_id"),
    }


d = load()

if d["health"] is None or d["health"].empty or "error" in d["health"].columns:
    st.warning("No Phase 16 data. Run init_phase16_ops.py and run_phase16_ops.py")
    st.stop()

up = (d["health"]["status"] == "UP").sum()
total = len(d["health"])
c1, c2, c3 = st.columns(3)
c1.metric("Components UP", f"{up}/{total}")
c2.metric("Report runs", len(d["reports"]) if d["reports"] is not None else 0)
c3.metric(
    "Delivery log rows",
    len(d["deliveries"]) if d["deliveries"] is not None else 0,
)

st.subheader("System health")
st.dataframe(d["health"], width="stretch")
down = d["health"][d["health"]["status"] != "UP"]
if not down.empty:
    st.error("Some components are DOWN")
    st.dataframe(down, width="stretch")
else:
    st.success("All checked components UP")

st.subheader("Automated reports")
if d["reports"] is not None and not d["reports"].empty and "error" not in d["reports"].columns:
    st.dataframe(d["reports"].drop(columns=["summary_text"], errors="ignore"), width="stretch")
    st.text_area("Latest summary", d["reports"].iloc[0].get("summary_text") or "", height=220)
else:
    st.caption("No report runs")

st.subheader("Alert delivery log (dry-run)")
if d["deliveries"] is not None and not d["deliveries"].empty and "error" not in d["deliveries"].columns:
    st.dataframe(d["deliveries"], width="stretch")
else:
    st.caption("No delivery rows")

st.subheader("Role registry (Phase 8)")
if d["roles"] is not None and not d["roles"].empty and "error" not in d["roles"].columns:
    st.dataframe(d["roles"], width="stretch")
else:
    st.caption("No user_roles table data")

st.subheader("API usage counters")
if d["api"] is not None and not d["api"].empty and "error" not in d["api"].columns:
    st.dataframe(d["api"], width="stretch")
    st.caption("Counters start at 0 until the API increments them.")
else:
    st.caption("No API usage rows")

st.info(
    "External email/WhatsApp send is dry-run only. Wire real providers under controlled credentials."
)
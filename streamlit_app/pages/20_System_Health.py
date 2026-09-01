"""OceanWatch — Platform System Health (canvas Level 8)."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

st.set_page_config(page_title="System Health", page_icon=":material/settings:", layout="wide")
st.title("System Health")
st.caption("Prototype posture checks · not a production SRE console")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
API = "http://localhost:8000"


@st.cache_data(ttl=30)
def db_checks():
    eng = create_engine(DB, pool_pre_ping=True)
    out = {"ok": False, "error": None, "tables": {}, "alerts": None}
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            out["ok"] = True
            for t in (
                "fact_ocean_conditions",
                "fact_alerts",
                "fact_ais_positions",
                "fact_gfw_fishing_effort",
                "fact_wio_intelligence_index",
                "fact_vessel_anomalies",
                "fact_port_metrics",
            ):
                try:
                    n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    out["tables"][t] = int(n or 0)
                except Exception:
                    out["tables"][t] = None
            try:
                out["alerts"] = pd.read_sql(
                    text(
                        """
                        SELECT status, COUNT(*) AS n
                        FROM fact_alerts
                        GROUP BY status
                        ORDER BY 1
                        """
                    ),
                    conn,
                )
            except Exception:
                out["alerts"] = pd.DataFrame()
    except Exception as e:
        out["error"] = str(e)
    return out


def api_check():
    if requests is None:
        return {"ok": False, "detail": "requests not installed"}
    try:
        r = requests.get(f"{API}/health", timeout=5)
        return {"ok": r.status_code == 200, "status_code": r.status_code, "body": r.json()}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


c1, c2, c3 = st.columns(3)
db = db_checks()
api = api_check()

c1.metric("PostgreSQL", "UP" if db["ok"] else "DOWN")
c2.metric("API /health", "UP" if api.get("ok") else "DOWN")
c3.metric("Checked at", datetime.utcnow().strftime("%H:%M UTC"))

if db.get("error"):
    st.error(f"DB: {db['error']}")
if not api.get("ok"):
    st.warning(f"API: {api.get('detail') or api}")

st.subheader("Core table row counts")
rows = [{"table": k, "rows": v} for k, v in (db.get("tables") or {}).items()]
st.dataframe(pd.DataFrame(rows), width="stretch")

st.subheader("Alert status")
if db.get("alerts") is not None and not db["alerts"].empty:
    st.dataframe(db["alerts"], width="stretch")
else:
    st.caption("No alert status breakdown.")

st.subheader("API response")
st.json(api)

st.info(
    "Decision-support prototype. Green checks mean local stack is reachable, "
    "not that operational SLAs are met."
)
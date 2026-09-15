"""Phase 25 — Partner API access & audit trail."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Partner Access",
    page_icon=":material/vpn_key:",
    layout="wide",
)
st.title("Partner Access & Audit")
st.caption(
    "API clients, hashed keys, usage samples, and platform audit log. "
    "Demo keys are hashed — plaintext is never stored in the database."
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "clients": q("SELECT * FROM dim_api_clients ORDER BY client_id"),
        "keys": q(
            """
            SELECT key_id, client_id, key_prefix, scopes, rate_limit_per_day,
                   status, expires_at, created_at
            FROM dim_api_keys
            ORDER BY client_id
            """
        ),
        "usage": q(
            """
            SELECT * FROM fact_api_usage
            ORDER BY requested_at DESC
            LIMIT 200
            """
        ),
        "audit": q(
            """
            SELECT * FROM fact_audit_log
            ORDER BY created_at DESC
            LIMIT 200
            """
        ),
    }


d = load()

if d["clients"] is None or d["clients"].empty or "error" in d["clients"].columns:
    st.warning("No Phase 25 data. Run init_phase25_access.py and run_phase25_access.py")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Clients", len(d["clients"]))
c2.metric("API keys", len(d["keys"]) if d["keys"] is not None else 0)
c3.metric("Usage rows", len(d["usage"]) if d["usage"] is not None else 0)
c4.metric("Audit rows", len(d["audit"]) if d["audit"] is not None else 0)

st.subheader("Clients")
st.dataframe(d["clients"], width="stretch")

st.subheader("API keys (prefix only — hashes hidden from default view)")
st.dataframe(d["keys"], width="stretch")

st.subheader("Usage")
if d["usage"] is not None and not d["usage"].empty and "error" not in d["usage"].columns:
    st.dataframe(d["usage"], width="stretch")
    if "endpoint" in d["usage"].columns:
        st.bar_chart(d["usage"]["endpoint"].value_counts())
else:
    st.caption("No usage")

st.subheader("Audit log")
if d["audit"] is not None and not d["audit"].empty and "error" not in d["audit"].columns:
    st.dataframe(d["audit"], width="stretch")
else:
    st.caption("No audit rows")

st.info(
    "Wire FastAPI middleware next to validate key_hash on each request and append fact_api_usage. "
    "Rotate demo keys before any external share."
)
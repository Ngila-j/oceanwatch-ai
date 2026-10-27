"""Alert Subscriptions — Phase 8 preference store."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(
    page_title="Alert Subscriptions",
    page_icon=":material/mail:",
    layout="wide",
)

try:
    from ow_theme import apply_theme, init_a11y_defaults

    init_a11y_defaults()
    apply_theme()
except Exception:
    pass

st.title("Alert Subscriptions")
st.caption(
    "Phase 8 foundation: store preferences in PostgreSQL. "
    "Email/WhatsApp delivery is optional and off by default."
)


def _sa_uri(uri: str) -> str:
    if not uri:
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


DB = get_db_uri()
if not DB:
    st.error("No database URI configured (OCEANWATCH_DB_URI / DATABASE_URL).")
    st.stop()

engine = create_engine(_sa_uri(DB), pool_pre_ping=True)

ALERT_TYPES = [
    "PORT_RISK",
    "VESSEL_ANOMALY",
    "BLOOM_RISK",
    "SST_ANOMALY",
    "FISHING_ACTIVITY",
    "TIDE_RISK",
]


def _ensure_schema(conn) -> None:
    """Create product tables if missing (idempotent)."""
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id VARCHAR PRIMARY KEY,
                role VARCHAR NOT NULL,
                organization VARCHAR,
                access_level VARCHAR NOT NULL,
                email VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS alert_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR,
                role VARCHAR,
                organization VARCHAR,
                alert_type VARCHAR NOT NULL,
                region VARCHAR DEFAULT 'Kenya EEZ',
                severity_threshold VARCHAR DEFAULT 'MEDIUM',
                channel VARCHAR DEFAULT 'email',
                destination VARCHAR,
                email_enabled BOOLEAN DEFAULT TRUE,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


with st.form("sub_form"):
    user_id = st.text_input("User ID", value="demo_port")
    role = st.selectbox(
        "Role",
        ["port_operator", "fisheries_user", "maritime_user", "environment_user", "researcher"],
    )
    org = st.text_input("Organization", value="Demo Org")
    alert_type = st.selectbox("Alert type", ALERT_TYPES)
    severity = st.selectbox("Minimum severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], index=1)
    channel = st.selectbox("Channel", ["email", "webhook"])
    destination = st.text_input("Destination (email or URL)")
    email_enabled = st.checkbox("Email enabled", value=True)
    submitted = st.form_submit_button("Save subscription")

if submitted:
    try:
        with engine.begin() as conn:
            _ensure_schema(conn)
            conn.execute(
                text(
                    """
                    INSERT INTO alert_subscriptions (
                        user_id, role, organization, alert_type, region,
                        severity_threshold, channel, destination, email_enabled, active
                    ) VALUES (
                        :user_id, :role, :org, :alert_type, 'Kenya EEZ',
                        :severity, :channel, :destination, :email_enabled, TRUE
                    )
                    """
                ),
                {
                    "user_id": user_id.strip() or "anonymous",
                    "role": role,
                    "org": org.strip() or None,
                    "alert_type": alert_type,
                    "severity": severity,
                    "channel": channel,
                    "destination": (destination or "").strip() or None,
                    "email_enabled": bool(email_enabled),
                },
            )
        st.success("Subscription saved to PostgreSQL.")
        st.cache_data.clear()
    except Exception as e:  # noqa: BLE001
        st.error(f"Save failed: {e}")


@st.cache_data(ttl=30)
def load_subs():
    try:
        with engine.begin() as conn:
            _ensure_schema(conn)
        df = pd.read_sql(
            text(
                """
                SELECT id, user_id, role, organization, alert_type, region,
                       severity_threshold, channel, destination, email_enabled,
                       active, created_at
                FROM alert_subscriptions
                ORDER BY created_at DESC NULLS LAST
                LIMIT 50
                """
            ),
            engine,
        )
        return df, None
    except Exception as e:  # noqa: BLE001
        return pd.DataFrame(), str(e)


st.subheader("Current subscriptions")
subs, err = load_subs()
if err:
    low = str(err).lower()
    if "does not exist" in low or "undefinedtable" in low:
        st.warning(
            "`alert_subscriptions` is missing. Run "
            "`python ingestion/init_phase8_product.py`, then refresh."
        )
    else:
        st.error(f"Could not load subscriptions: {err}")
elif subs is None or subs.empty:
    st.info("No subscriptions yet. Save one above, or run Phase 8 init for demo rows.")
else:
    st.dataframe(subs, use_container_width=True, hide_index=True)
    st.caption(f"{len(subs)} subscription(s)")

st.caption(
    "WhatsApp is a stretch goal. Production email needs SMTP credentials in env "
    "(never commit secrets). This page only persists preferences."
)

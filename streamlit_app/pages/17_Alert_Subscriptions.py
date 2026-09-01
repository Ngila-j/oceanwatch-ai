import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Alert Subscriptions", page_icon="ðŸ“§", layout="wide")
st.title("ðŸ“§ Alert Subscriptions")
st.caption(
    "Phase 8 foundation: store preferences in PostgreSQL. "
    "Email/WhatsApp delivery is optional and off by default."
)

engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")

ALERT_TYPES = [
    "PORT_RISK",
    "VESSEL_ANOMALY",
    "BLOOM_RISK",
    "SST_ANOMALY",
    "FISHING_ACTIVITY",
    "TIDE_RISK",
]

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
                conn.execute(
                    text(
                        """
                        INSERT INTO alert_subscriptions
                        (user_id, role, organization, alert_type, region,
                         severity_threshold, channel, destination, email_enabled, active)
                        VALUES
                        (:user_id, :role, :org, :alert_type, 'Kenya EEZ',
                         :severity, :channel, :destination, :email_enabled, TRUE)
                        """
                    ),
                    {
                        "user_id": user_id,
                        "role": role,
                        "org": org,
                        "alert_type": alert_type,
                        "severity": severity,
                        "channel": channel,
                        "destination": destination,
                        "email_enabled": email_enabled,
                    },
                )
            st.success("Subscription saved to PostgreSQL.")
        except Exception as e:
            st.error(f"Save failed: {e}")

st.subheader("Current subscriptions")
try:
    subs = pd.read_sql(
        "SELECT * FROM alert_subscriptions ORDER BY created_at DESC LIMIT 50",
        engine,
    )
    st.dataframe(subs, width="stretch")
except Exception as e:
    st.warning(f"Could not load subscriptions: {e}")

st.info(
    "WhatsApp is a stretch goal. Production email needs SMTP credentials in env "
    "(never commit secrets). This page only persists preferences."
)
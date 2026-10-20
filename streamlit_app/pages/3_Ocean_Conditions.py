import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        return "postgresql+psycopg2://postgres:password@localhost:5433/oceanwatch_db"


try:
    from ow_theme import page_header, close_page
except ImportError:

    def page_header(title, subtitle=""):
        st.title(title)
        if subtitle:
            st.caption(subtitle)

    def close_page():
        pass


page_header("Ocean Conditions", "SST, chlorophyll, and tide trends (Kenya EEZ)")


@st.cache_data(ttl=300)
def load_data():
    engine = create_engine(get_db_uri(), pool_pre_ping=True)
    try:
        df = pd.read_sql(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3,
                   tide_mean_m, tide_min_m, tide_max_m
            FROM fact_ocean_conditions
            ORDER BY date_key
            """,
            engine,
        )
        return df
    except Exception as exc:
        st.warning(f"Ocean conditions unavailable: {exc.__class__.__name__}: {exc}")
        return pd.DataFrame()


df = load_data()

if df is None or df.empty:
    st.info(
        "No ocean condition rows yet. After connecting Supabase, run:\n\n"
        "`python ingestion/seed_ocean_conditions.py`"
    )
    try:
        close_page()
    except Exception:
        pass
    st.stop()

c1, c2, c3 = st.columns(3)
latest = df.iloc[-1]
c1.metric("Latest SST (°C)", f"{float(latest['sst_celsius']):.2f}")
c2.metric("Latest CHL (mg/m³)", f"{float(latest['chlorophyll_mg_m3']):.3f}")
if pd.notna(latest.get("tide_mean_m")):
    c3.metric("Tide mean (m)", f"{float(latest['tide_mean_m']):.2f}")
else:
    c3.metric("Tide mean (m)", "—")

st.subheader("Sea surface temperature")
fig_sst = px.line(df, x="date_key", y="sst_celsius", markers=True)
st.plotly_chart(fig_sst, width="stretch")

st.subheader("Chlorophyll-a")
fig_chl = px.line(df, x="date_key", y="chlorophyll_mg_m3", markers=True)
st.plotly_chart(fig_chl, width="stretch")

if "tide_mean_m" in df.columns and df["tide_mean_m"].notna().any():
    st.subheader("Tide range")
    fig_tide = px.line(
        df,
        x="date_key",
        y=["tide_min_m", "tide_mean_m", "tide_max_m"],
        markers=True,
    )
    st.plotly_chart(fig_tide, width="stretch")

st.dataframe(df.tail(14), width="stretch", hide_index=True)

try:
    close_page()
except Exception:
    pass

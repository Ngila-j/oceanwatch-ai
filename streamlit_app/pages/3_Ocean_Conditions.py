import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="Ocean Conditions", page_icon="🌊", layout="wide")
st.title("🌊 Ocean Conditions Trends")

@st.cache_data(ttl=300)
def load_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    df = pd.read_sql("""
        SELECT date_key, sst_celsius, chlorophyll_mg_m3,
               tide_mean_m, tide_min_m, tide_max_m
        FROM fact_ocean_conditions
        ORDER BY date_key
    """, engine)
    return df

df = load_data()

if df.empty:
    st.warning("No data available.")
else:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Sea Surface Temperature (°C)")
        fig_sst = px.line(df.dropna(subset=["sst_celsius"]), 
                          x="date_key", y="sst_celsius",
                          markers=True)
        st.plotly_chart(fig_sst, use_container_width=True)

    with col2:
        st.subheader("Chlorophyll-a (mg/m³)")
        fig_chl = px.line(df.dropna(subset=["chlorophyll_mg_m3"]), 
                          x="date_key", y="chlorophyll_mg_m3",
                          markers=True, color_discrete_sequence=["green"])
        st.plotly_chart(fig_chl, use_container_width=True)

    st.subheader("Tide Statistics")
    fig_tide = px.line(df.dropna(subset=["tide_mean_m"]), 
                       x="date_key", y=["tide_min_m", "tide_mean_m", "tide_max_m"],
                       markers=True)
    st.plotly_chart(fig_tide, use_container_width=True)
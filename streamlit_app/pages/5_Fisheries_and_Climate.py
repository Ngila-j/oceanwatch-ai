import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="Fisheries & Climate", page_icon="🐟", layout="wide")
st.title("🐟 Fisheries & Climate Indicators")

@st.cache_data(ttl=300)
def load_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    return pd.read_sql("""
        SELECT date_key, sst_celsius, chlorophyll_mg_m3
        FROM fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL OR chlorophyll_mg_m3 IS NOT NULL
        ORDER BY date_key
    """, engine)

df = load_data()

st.markdown("""
Chlorophyll and Sea Surface Temperature are key indicators for primary productivity and fish habitat suitability in the Western Indian Ocean.
""")

if df.empty:
    st.warning("No data available.")
else:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("SST Trend")
        fig = px.line(df.dropna(subset=["sst_celsius"]), x="date_key", y="sst_celsius", markers=True)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Chlorophyll Trend")
        fig = px.line(df.dropna(subset=["chlorophyll_mg_m3"]), x="date_key", y="chlorophyll_mg_m3",
                      markers=True, color_discrete_sequence=["#2ca02c"])
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Interpretation Guide")
    st.markdown("""
    - **Higher Chlorophyll** → higher primary productivity → potentially better fishing conditions  
    - **SST > 29–30°C** → possible thermal stress for some species  
    - Combination of moderate SST + elevated chlorophyll is often favourable for pelagic species
    """)
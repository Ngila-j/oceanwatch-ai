"""Phase 18 — Regional coverage hierarchy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri() -> str:
        try:
            from dotenv import load_dotenv

            load_dotenv(_APP.parent / "ingestion" / ".env")
        except ImportError:
            pass
        return (
            os.getenv("OCEANWATCH_DB_URI")
            or os.getenv("DATABASE_URL")
            or "postgresql://postgres:password@localhost:5433/oceanwatch_db"
        )


try:
    from components.pagekit import boot, close_page
except ImportError:
    def boot(title: str, description: str = "", **_kwargs):
        try:
            st.set_page_config(page_title=title, page_icon="🗺️", layout="wide")
        except Exception:
            pass
        st.title(title)
        if description:
            st.caption(description)

    def close_page(**_kwargs):
        pass


boot(
    "Regional Coverage",
    "Western Indian Ocean hierarchy — Kenya ACTIVE; peers PLANNED. "
    "One pipeline design, filter by country_id / region_id.",
)


def _engine():
    uri = get_db_uri().strip()
    if uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    args: dict = {"connect_timeout": 15}
    if "supabase" in uri or "pooler" in uri or "sslmode=" in uri:
        args["sslmode"] = "require"
    return create_engine(uri, pool_pre_ping=True, connect_args=args)


def _is_missing_relation(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "undefinedtable" in msg or "does not exist" in msg


@st.cache_data(ttl=120, show_spinner=False)
def load_table(sql: str) -> pd.DataFrame:
    eng = _engine()
    with eng.connect() as conn:
        return pd.read_sql(text(sql), conn)


def safe_load(label: str, sql: str) -> pd.DataFrame:
    try:
        return load_table(sql)
    except Exception as e:
        if _is_missing_relation(e):
            st.warning(
                f"**{label}** not found. Run `init_phase18_regions.py` then "
                "`run_phase18_regions.py`."
            )
        else:
            st.error(f"Could not load {label}: {e}")
        return pd.DataFrame()


def add_centroids(df: pd.DataFrame) -> pd.DataFrame:
    """Derive map points from bbox when centroid_* columns are absent."""
    if df.empty:
        return df
    out = df.copy()
    if "centroid_lat" not in out.columns and {"min_lat", "max_lat"} <= set(out.columns):
        out["centroid_lat"] = (pd.to_numeric(out["min_lat"], errors="coerce") + pd.to_numeric(out["max_lat"], errors="coerce")) / 2.0
    if "centroid_lon" not in out.columns and {"min_lon", "max_lon"} <= set(out.columns):
        out["centroid_lon"] = (pd.to_numeric(out["min_lon"], errors="coerce") + pd.to_numeric(out["max_lon"], errors="coerce")) / 2.0
    return out


countries = safe_load("dim_countries", "SELECT * FROM dim_countries ORDER BY country_id")
regions = safe_load("dim_regions", "SELECT * FROM dim_regions ORDER BY country_id, region_id")
ports = safe_load("dim_ports_ref", "SELECT * FROM dim_ports_ref ORDER BY country_id, port_name")
zones = safe_load(
    "dim_marine_zones",
    """
    SELECT * FROM dim_marine_zones
    ORDER BY COALESCE(zone_id, zone_key), zone_name
    """,
)

# KPIs
c1, c2, c3, c4 = st.columns(4)
n_countries = len(countries) if not countries.empty else 0
n_regions = len(regions) if not regions.empty else 0
n_active = int((regions["status"].astype(str).str.upper() == "ACTIVE").sum()) if not regions.empty and "status" in regions.columns else 0
n_planned = int((regions["status"].astype(str).str.upper() == "PLANNED").sum()) if not regions.empty and "status" in regions.columns else 0
c1.metric("Countries", n_countries)
c2.metric("Regions", n_regions)
c3.metric("ACTIVE regions", n_active)
c4.metric("PLANNED regions", n_planned)

tab_c, tab_r, tab_p, tab_z, tab_map = st.tabs(
    ["Countries", "Regions", "Ports", "Marine zones", "Map"]
)

with tab_c:
    if countries.empty:
        st.info("No countries seeded yet.")
    else:
        st.dataframe(countries, use_container_width=True, hide_index=True)

with tab_r:
    if regions.empty:
        st.info("No regions seeded yet.")
    else:
        st.dataframe(regions, use_container_width=True, hide_index=True)
        st.caption(
            "Pipelines should filter facts with `country_id` / `region_id` — "
            "do not fork DAGs per country."
        )

with tab_p:
    if ports.empty:
        st.info("No reference ports seeded yet.")
    else:
        st.dataframe(ports, use_container_width=True, hide_index=True)

with tab_z:
    if zones.empty:
        st.info("No marine zones seeded yet.")
    else:
        st.dataframe(zones, use_container_width=True, hide_index=True)
        st.caption("MPA rows may be DEMO proxies until official polygons are licensed.")

with tab_map:
    reg = add_centroids(regions)
    has_pts = (
        not reg.empty
        and "centroid_lat" in reg.columns
        and "centroid_lon" in reg.columns
        and reg[["centroid_lat", "centroid_lon"]].notna().all(axis=1).any()
    )
    if not has_pts:
        st.info("No region coordinates available for the map.")
    else:
        plot_df = reg.dropna(subset=["centroid_lat", "centroid_lon"]).copy()
        color_col = "status" if "status" in plot_df.columns else None
        hover = [c for c in ("region_id", "region_name", "country_id", "status", "region_type") if c in plot_df.columns]
        fig = px.scatter(
            plot_df,
            lat="centroid_lat",
            lon="centroid_lon",
            color=color_col,
            hover_data=hover or None,
            title="Region centroids (bounding boxes → center points)",
        )
        fig.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=480)
        fig.update_geos(
            fitbounds="locations",
            showcoastlines=True,
            showland=True,
            landcolor="rgb(235,240,235)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Optional port overlay
        if not ports.empty and {"lat", "lon"} <= set(ports.columns):
            p2 = ports.dropna(subset=["lat", "lon"])
            if not p2.empty:
                fig_p = px.scatter(
                    p2,
                    lat="lat",
                    lon="lon",
                    hover_name="port_name" if "port_name" in p2.columns else None,
                    color="status" if "status" in p2.columns else None,
                    title="Reference ports",
                )
                fig_p.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=360)
                fig_p.update_geos(fitbounds="locations", showcoastlines=True)
                st.plotly_chart(fig_p, use_container_width=True)

st.divider()
st.markdown(
    """
**Design notes**
- **ACTIVE** = operational filters and demos (Kenya first).
- **PLANNED** = same schema and jobs; flip status when coverage expands.
- Bounding boxes are operational monitoring boxes for pipeline filtering — not legal EEZ claims.
"""
)

close_page(methodology=True, attribution=True)

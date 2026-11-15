"""Mombasa Port Ops Board — KPA + AIS + marine fusion."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row
from services.port_ops_board import PortOpsBoardService

try:
    import plotly.express as px

    HAS_PX = True
except Exception:  # noqa: BLE001
    HAS_PX = False

boot(
    "Port Ops Board — Mombasa",
    "Fused KPA 14-day list · near-port AIS · vessel name match · free marine weather.",
    chips=[
        ("KPA + AIS", "primary"),
        ("Live marine", "info"),
        ("Ops fusion", "success"),
    ],
)

with st.sidebar:
    st.markdown("#### Board controls")
    radius = st.slider("AIS radius (nm)", 10, 80, 40, 5)
    hours = st.slider("AIS lookback (h)", 6, 72, 36, 6)
    min_match = st.slider("Min name match", 0.40, 0.90, 0.55, 0.05)
    if st.button("Reload board", use_container_width=True):
        st.cache_data.clear()


@st.cache_data(ttl=90, show_spinner=False)
def _pack(radius_nm: float, ais_hours: int, match_min: float):
    return PortOpsBoardService().load_pack(
        ais_radius_nm=radius_nm, ais_hours=ais_hours, match_min=match_min
    )


with st.spinner("Building Mombasa ops board…"):
    try:
        pack = _pack(float(radius), int(hours), float(min_match))
    except Exception as exc:  # noqa: BLE001
        banner("Board failed to load", str(exc), tone="danger")
        close_page()
        st.stop()

k = pack.kpis

kpi_row(
    [
        {
            "label": "KPA vessels",
            "value": str(k.get("kpa_vessels") or 0),
            "hint": f"report {k.get('kpa_report_date') or '—'}",
            "tone": "primary",
        },
        {
            "label": "AIS near-port",
            "value": str(k.get("ais_near") or 0),
            "hint": f"{radius} nm · {hours}h",
            "tone": "info",
        },
        {
            "label": "KPA↔AIS matches",
            "value": str(k.get("matches") or 0),
            "hint": f"{k.get('match_rate_pct') or 0}% match rate",
            "tone": "success" if (k.get("matches") or 0) else "warning",
        },
        {
            "label": "ETA ≤48h",
            "value": str(k.get("arrivals_48h") or 0),
            "hint": "from KPA list",
            "tone": "warning" if (k.get("arrivals_48h") or 0) >= 8 else "primary",
        },
        {
            "label": "Wave height",
            "value": f"{float(k['wave_m']):.1f} m" if k.get("wave_m") is not None else "—",
            "hint": "Open-Meteo Mombasa",
            "tone": "warning"
            if k.get("wave_m") is not None and float(k["wave_m"]) >= 2.0
            else "info",
        },
        {
            "label": "Wind",
            "value": f"{float(k['wind_ms']):.1f} m/s" if k.get("wind_ms") is not None else "—",
            "hint": f"air {k.get('temp_c') or '—'} °C",
            "tone": "info",
        },
    ]
)

# Alerts
for a in pack.alerts[:5]:
    tone = {
        "CRITICAL": "danger",
        "HIGH": "danger",
        "WATCH": "warning",
        "INFO": "info",
    }.get(str(a.get("severity")), "info")
    banner(f"{a.get('severity')}: {a.get('title')}", a.get("detail") or "", tone=tone)

st.markdown("#### Command brief")
st.markdown(pack.brief)

tab_board, tab_match, tab_ais, tab_mix, tab_wx, tab_export = st.tabs(
    [
        "Arrival board",
        "KPA ↔ AIS match",
        "AIS near-port",
        "Berth · agent · cargo",
        "Weather & marine",
        "Export",
    ]
)

with tab_board:
    st.markdown("##### Expected movements (KPA) with AIS overlay")
    board = pack.arrival_board
    if board.empty:
        empty_state(
            "No arrival board",
            "Upload a KPA 14-day DOCX on Live Feeds & KPA List first.",
            icon="📄",
        )
        st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Open KPA upload →")
    else:
        # highlight filter
        f1, f2 = st.columns(2)
        only_soon = f1.checkbox("Only next 72h ETAs", value=False)
        only_matched = f2.checkbox("Only AIS-matched", value=False)
        view = board.copy()
        if only_soon and "hours_to_eta" in view.columns:
            h = pd.to_numeric(view["hours_to_eta"], errors="coerce")
            view = view[h.isna() | ((h >= -6) & (h <= 72))]
        if only_matched and "ais_status" in view.columns:
            view = view[view["ais_status"].astype(str) != "NO AIS"]
        st.dataframe(view, width="stretch", hide_index=True, height=420)
        if HAS_PX and "hours_to_eta" in view.columns:
            plot_df = view.dropna(subset=["hours_to_eta"]).head(40)
            if not plot_df.empty:
                fig = px.bar(
                    plot_df,
                    x="vessel",
                    y="hours_to_eta",
                    color="ais_status",
                    title="Hours to ETA (negative = overdue vs now)",
                    labels={"hours_to_eta": "Hours to ETA", "vessel": "Vessel"},
                )
                fig.update_layout(xaxis_tickangle=-40, height=360, margin=dict(t=40, b=80))
                st.plotly_chart(fig, use_container_width=True)

with tab_match:
    st.markdown("##### Fuzzy name match (KPA list ↔ live AIS)")
    st.caption(
        "Token / containment similarity on vessel names. "
        "False positives possible — treat as operator assist, not identity proof."
    )
    m = pack.matches
    if m.empty:
        empty_state(
            "No matches",
            "Need both KPA rows and AIS positions with vessel names in range.",
            icon="🔗",
        )
    else:
        st.dataframe(m, width="stretch", hide_index=True)
        c1, c2 = st.columns(2)
        c1.metric("Matched", len(m))
        c2.metric("Unmatched KPA", len(pack.unmatched_kpa))
        if not pack.unmatched_kpa.empty:
            with st.expander("Unmatched KPA vessels"):
                cols = [
                    c
                    for c in ("vessel_name", "eta", "berth", "agent", "cargo")
                    if c in pack.unmatched_kpa.columns
                ]
                st.dataframe(
                    pack.unmatched_kpa[cols] if cols else pack.unmatched_kpa,
                    width="stretch",
                    hide_index=True,
                )

with tab_ais:
    ais = pack.ais_near
    st.markdown("##### AIS positions near Mombasa")
    if ais.empty:
        empty_state(
            "No AIS in box",
            "Run fetch_ais_realtime.py with AISSTREAM_API_KEY, or widen radius/lookback.",
            icon="📡",
        )
    else:
        st.dataframe(ais.head(300), width="stretch", hide_index=True)
        if HAS_PX and {"lat", "lon"}.issubset(ais.columns):
            fig = px.scatter_mapbox(
                ais,
                lat="lat",
                lon="lon",
                color="dist_nm" if "dist_nm" in ais.columns else None,
                hover_name="vessel_name" if "vessel_name" in ais.columns else None,
                hover_data=[c for c in ("mmsi", "sog", "dist_nm") if c in ais.columns],
                zoom=8,
                height=440,
                title="Near-port AIS",
            )
            fig.update_layout(mapbox_style="open-street-map", margin=dict(t=40, l=0, r=0, b=0))
            # Mombasa marker via center
            fig.update_mapboxes(center={"lat": -4.0435, "lon": 39.6682})
            st.plotly_chart(fig, use_container_width=True)

with tab_mix:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Berth load (KPA)")
        if pack.berth_load.empty:
            st.caption("No berth field on KPA rows.")
        else:
            st.dataframe(pack.berth_load, width="stretch", hide_index=True)
            if HAS_PX:
                fig = px.bar(pack.berth_load.head(12), x="berth", y="vessels", title="Vessels by berth")
                st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("##### Top agents")
        if pack.agent_mix.empty:
            st.caption("No agent field.")
        else:
            st.dataframe(pack.agent_mix, width="stretch", hide_index=True)
    st.markdown("##### Cargo mix")
    if pack.cargo_mix.empty:
        st.caption("No cargo field.")
    else:
        st.dataframe(pack.cargo_mix, width="stretch", hide_index=True)
        if HAS_PX:
            fig = px.pie(pack.cargo_mix.head(10), names="cargo", values="vessels", title="Cargo (top 10)")
            st.plotly_chart(fig, use_container_width=True)

with tab_wx:
    st.markdown("##### Mombasa weather & marine (free Open-Meteo)")
    w1, w2 = st.columns(2)
    with w1:
        st.markdown("**Weather**")
        if not pack.weather:
            st.info("No weather row — open Live Feeds and click Refresh.")
            st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Refresh free feeds →")
        else:
            st.json(
                {
                    k2: pack.weather.get(k2)
                    for k2 in (
                        "observed_at",
                        "temp_c",
                        "humidity_pct",
                        "wind_ms",
                        "wind_dir_deg",
                        "precip_mm",
                        "pressure_hpa",
                        "cloud_pct",
                        "weather_code",
                    )
                    if k2 in pack.weather
                }
            )
    with w2:
        st.markdown("**Marine**")
        if not pack.marine:
            st.info("No marine row — refresh free feeds.")
        else:
            st.json(
                {
                    k2: pack.marine.get(k2)
                    for k2 in (
                        "observed_at",
                        "wave_height_m",
                        "wave_period_s",
                        "wave_dir_deg",
                        "swell_height_m",
                        "swell_period_s",
                        "sea_temp_c",
                    )
                    if k2 in pack.marine
                }
            )

with tab_export:
    st.markdown("##### Download fused board")
    if not pack.arrival_board.empty:
        st.download_button(
            "Arrival board CSV",
            data=pack.arrival_board.to_csv(index=False).encode("utf-8"),
            file_name="mombasa_arrival_board.csv",
            mime="text/csv",
        )
    if not pack.matches.empty:
        st.download_button(
            "KPA–AIS matches CSV",
            data=pack.matches.to_csv(index=False).encode("utf-8"),
            file_name="mombasa_kpa_ais_matches.csv",
            mime="text/csv",
        )
    if not pack.kpa.empty:
        st.download_button(
            "Full KPA snapshot CSV",
            data=pack.kpa.to_csv(index=False).encode("utf-8"),
            file_name="mombasa_kpa_snapshot.csv",
            mime="text/csv",
        )
    if pack.errors:
        with st.expander("Loader notes"):
            for e in pack.errors:
                st.code(e)

st.markdown("---")
b1, b2, b3 = st.columns(3)
with b1:
    st.page_link("pages/8_Port_Intelligence.py", label="Port Intelligence →")
with b2:
    st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Live Feeds & KPA →")
with b3:
    st.page_link("pages/11_AIS_Live.py", label="AIS Live →")

close_page()

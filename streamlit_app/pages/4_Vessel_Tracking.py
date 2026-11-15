"""
Vessel Tracking & AIS Analytics
================================
Historical + near real-time AIS tracks, Mombasa port calls, anomaly flags,
and Global Fishing Watch effort layers for Kenya EEZ / WIO.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from components.pagekit import boot, close_page  # noqa: E402
from components.ui import banner, kpi_row  # noqa: E402

try:
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium

    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    from services.vessel_tracking import MAP_CENTER, VesselTrackingService
except ImportError:  # pragma: no cover
    from streamlit_app.services.vessel_tracking import (  # type: ignore
        MAP_CENTER,
        VesselTrackingService,
    )


def _resolve_db_uri() -> str:
    try:
        import sys as _sys
        from pathlib import Path as _P

        ing = _P(__file__).resolve().parents[2] / "ingestion"
        if str(ing) not in _sys.path:
            _sys.path.insert(0, str(ing))
        from db_utils import get_db_uri as _ing  # type: ignore

        return _ing()
    except Exception:  # noqa: BLE001
        pass
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        from streamlit_app.db_config import get_db_uri  # type: ignore

        return get_db_uri()


boot(
    "Vessel Tracking & AIS Analytics",
    "Historical and near real-time AIS tracks · Mombasa port calls · "
    "anomaly flags · Global Fishing Watch layers for Kenya EEZ.",
    chips=[
        ("AIS", "primary"),
        ("Mombasa", "info"),
        ("GFW", "info"),
        ("Anomalies", "warning"),
    ],
)


@st.cache_resource(show_spinner=False)
def _svc() -> VesselTrackingService:
    return VesselTrackingService(db_uri=_resolve_db_uri())


def _lat_lon(df: pd.DataFrame) -> tuple[str | None, str | None]:
    lat = next((c for c in ("lat", "latitude", "last_lat", "cell_lat") if c in df.columns), None)
    lon = next((c for c in ("lon", "longitude", "last_lon", "cell_lon") if c in df.columns), None)
    return lat, lon


def _sog_series(df: pd.DataFrame) -> pd.Series:
    for c in ("sog", "last_sog", "speed_mean", "avg_sog"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return pd.Series([pd.NA] * len(df), index=df.index)


def _build_map(
    *,
    vessels: pd.DataFrame,
    track: pd.DataFrame | None,
    geofences: pd.DataFrame | None,
    gfw: pd.DataFrame | None,
    port_events: pd.DataFrame | None,
    selected_mmsi: str | None,
    show_gfw: bool,
    show_ports: bool,
) -> "folium.Map":
    m = folium.Map(location=list(MAP_CENTER), zoom_start=6, tiles="CartoDB positron")

    folium.Rectangle(
        bounds=[[-5.5, 38.5], [2.5, 45.5]],
        color="#0B3D5C",
        weight=1,
        fill=False,
        dash_array="4",
        tooltip="Kenya / WIO analysis box",
    ).add_to(m)

    # Mombasa approaches highlight
    folium.Rectangle(
        bounds=[[-4.2, 39.5], [-3.9, 39.8]],
        color="#C45C26",
        weight=2,
        fill=True,
        fill_opacity=0.06,
        tooltip="Mombasa port approaches",
    ).add_to(m)

    if geofences is not None and not geofences.empty:
        for _, g in geofences.head(40).iterrows():
            name = str(g.get("fence_name") or g.get("fence_id") or "geofence")
            if {"min_lat", "max_lat", "min_lon", "max_lon"}.issubset(g.index):
                try:
                    folium.Rectangle(
                        bounds=[
                            [float(g["min_lat"]), float(g["min_lon"])],
                            [float(g["max_lat"]), float(g["max_lon"])],
                        ],
                        color="#7C3AED",
                        weight=1,
                        fill=True,
                        fill_opacity=0.04,
                        tooltip=name,
                    ).add_to(m)
                except (TypeError, ValueError):
                    pass

    if show_gfw and gfw is not None and not gfw.empty:
        glat, glon = _lat_lon(gfw)
        hours_col = next(
            (c for c in ("fishing_hours", "effort_hours", "hours", "vessel_hours") if c in gfw.columns),
            None,
        )
        if glat and glon:
            gfw_layer = folium.FeatureGroup(name="GFW fishing effort", show=True)
            sample = gfw.dropna(subset=[glat, glon]).head(400)
            for _, row in sample.iterrows():
                try:
                    hrs = float(row[hours_col]) if hours_col and pd.notna(row.get(hours_col)) else 1.0
                except (TypeError, ValueError):
                    hrs = 1.0
                radius = max(3, min(14, hrs * 2))
                folium.CircleMarker(
                    location=[float(row[glat]), float(row[glon])],
                    radius=radius,
                    color="#059669",
                    fill=True,
                    fill_opacity=0.35,
                    weight=0,
                    tooltip=f"GFW effort ~{hrs:.1f}h",
                ).add_to(gfw_layer)
            gfw_layer.add_to(m)

    if show_ports and port_events is not None and not port_events.empty:
        plat, plon = _lat_lon(port_events)
        port_layer = folium.FeatureGroup(name="Port calls", show=True)
        for _, row in port_events.head(80).iterrows():
            et = str(row.get("event_type") or "").upper()
            color = "#16A34A" if "ARRIV" in et else ("#DC2626" if "DEPART" in et else "#2563EB")
            lat = row.get(plat) if plat else row.get("lat")
            lon = row.get(plon) if plon else row.get("lon")
            # default Mombasa pin if no coords
            try:
                la = float(lat) if lat is not None and pd.notna(lat) else -4.05
                lo = float(lon) if lon is not None and pd.notna(lon) else 39.65
            except (TypeError, ValueError):
                la, lo = -4.05, 39.65
            folium.CircleMarker(
                location=[la, lo],
                radius=6,
                color=color,
                fill=True,
                fill_opacity=0.85,
                tooltip=f"{et} · MMSI {row.get('mmsi')} · {row.get('vessel_name') or ''}",
            ).add_to(port_layer)
        port_layer.add_to(m)

    lat_c, lon_c = _lat_lon(vessels) if vessels is not None else (None, None)
    if vessels is not None and not vessels.empty and lat_c and lon_c:
        cluster = MarkerCluster(name="Vessels").add_to(m)
        sogs = _sog_series(vessels)
        for idx, row in vessels.dropna(subset=[lat_c, lon_c]).head(500).iterrows():
            mmsi = str(row.get("mmsi", ""))
            name = str(row.get("vessel_name") or mmsi)
            sog = sogs.loc[idx] if idx in sogs.index else None
            flags = str(row.get("risk_flags") or "")
            color = "#0B6E4F"
            try:
                if sog is not None and float(sog) < 0.5:
                    color = "#6B7280"
            except (TypeError, ValueError):
                pass
            if "HIGH_RISK" in flags or "CRITICAL" in flags:
                color = "#B91C1C"
            elif "DARK" in flags or "LOITER" in flags:
                color = "#B45309"
            if selected_mmsi and mmsi == str(selected_mmsi):
                color = "#1D4ED8"
            folium.CircleMarker(
                location=[float(row[lat_c]), float(row[lon_c])],
                radius=6 if selected_mmsi and mmsi == str(selected_mmsi) else 4,
                color=color,
                fill=True,
                fill_opacity=0.9,
                tooltip=f"{name} · MMSI {mmsi} · SOG {sog}",
                popup=folium.Popup(
                    f"<b>{name}</b><br>MMSI {mmsi}<br>Type {row.get('vessel_type') or '—'}"
                    f"<br>Flag {row.get('flag') or '—'}<br>SOG {sog}"
                    f"<br>Flags: {flags or 'OK'}",
                    max_width=280,
                ),
            ).add_to(cluster)

    if track is not None and not track.empty:
        tlat, tlon = _lat_lon(track)
        if tlat and tlon:
            pts = track.dropna(subset=[tlat, tlon])[[tlat, tlon]].astype(float).values.tolist()
            if len(pts) >= 2:
                folium.PolyLine(
                    pts, color="#1D4ED8", weight=3.5, opacity=0.9, tooltip="AIS track"
                ).add_to(m)
                folium.Marker(pts[0], tooltip="Track start", icon=folium.Icon(color="green")).add_to(m)
                folium.Marker(pts[-1], tooltip="Latest", icon=folium.Icon(color="red")).add_to(m)
                m.fit_bounds(pts)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Filters")
    hours = st.slider("AIS lookback (hours)", 6, 168, 48, 6)
    only_kenya = st.checkbox("Kenya / WIO box only", value=True)
    search = st.text_input("Search MMSI / name / flag", placeholder="e.g. 634… or KENYA STAR")
    vtype = st.selectbox(
        "Vessel type",
        ["ALL", "CARGO", "TANKER", "FISHING", "TUG", "PASSENGER", "CONTAINER", "BULK", "OTHER", "UNKNOWN"],
    )
    flag_q = st.text_input("Flag contains", placeholder="Kenya, Panama…")
    sog_min, sog_max = st.slider("Speed over ground (kn)", 0.0, 30.0, (0.0, 30.0), 0.5)
    track_hours = st.slider("Track window (hours)", 6, 168, 72, 6)
    st.markdown("### Map layers")
    show_gfw = st.checkbox("GFW fishing effort", value=True)
    show_ports = st.checkbox("Port arrivals / departures", value=True)
    show_anoms = st.checkbox("Highlight risk flags", value=True)
    st.caption("Refresh: `python ingestion/run_vessel_tracking.py`")


svc = _svc()
with st.spinner("Loading fleet, port calls, and GFW layers…"):
    snap = svc.snapshot(
        hours=hours,
        only_kenya=only_kenya,
        search=search or None,
        vessel_type=None if vtype == "ALL" else vtype,
    )
    vessels = snap.vessels.copy() if snap.vessels is not None else pd.DataFrame()
    if not vessels.empty:
        vessels = svc.risk_flags(vessels)
        # speed filter
        sogs = _sog_series(vessels)
        if sogs.notna().any():
            mask = sogs.isna() | ((sogs >= sog_min) & (sogs <= sog_max))
            vessels = vessels.loc[mask]
        if flag_q.strip() and "flag" in vessels.columns:
            vessels = vessels[
                vessels["flag"].astype(str).str.contains(flag_q.strip(), case=False, na=False)
            ]
        elif flag_q.strip() and search:
            pass  # already searched via service when flag in dim
    k = svc.kpis(snap)
    port_act = svc.port_activity(port_name="Mombasa", days=max(7, hours // 24 + 1))
    if port_act.empty:
        port_act = svc.derive_port_calls_from_ais(hours=max(hours, 72))
    port_met = svc.port_metrics(port_name="Mombasa", days=30)
    gfw = svc.gfw_effort(days=30) if show_gfw else pd.DataFrame()
    beh = snap.behaviour if snap.behaviour is not None else pd.DataFrame()
    anom = snap.anomalies if snap.anomalies is not None else pd.DataFrame()

# KPIs
arrivals = 0
departures = 0
if not port_act.empty and "event_type" in port_act.columns:
    et = port_act["event_type"].astype(str).str.upper()
    arrivals = int(et.str.contains("ARRIV").sum())
    departures = int(et.str.contains("DEPART").sum())

risk_n = 0
if not vessels.empty and "risk_flags" in vessels.columns:
    risk_n = int(
        vessels["risk_flags"]
        .astype(str)
        .str.contains("HIGH_RISK|CRITICAL|DARK|LOITER", regex=True)
        .sum()
    )

if snap.errors:
    for e in snap.errors:
        banner("Data missing", str(e), tone="warning")

kpi_row(
    [
        {
            "label": "Tracked vessels",
            "value": f"{len(vessels):,}" if not vessels.empty else f"{k['vessels']:,}",
            "hint": f"last {hours}h AIS / profiles",
            "tone": "primary",
        },
        {
            "label": "In Kenya box",
            "value": f"{k['in_kenya_eez']:,}",
            "hint": "EEZ analysis window",
            "tone": "info",
        },
        {
            "label": "Mombasa arrivals",
            "value": f"{arrivals:,}",
            "hint": "port activity / AIS heuristic",
            "tone": "success" if arrivals else "info",
        },
        {
            "label": "Mombasa departures",
            "value": f"{departures:,}",
            "hint": "port activity / AIS heuristic",
            "tone": "info",
        },
        {
            "label": "Risk / anomaly flags",
            "value": f"{risk_n:,}",
            "hint": "loiter · dark cue · high risk",
            "tone": "danger" if risk_n else "success",
        },
        {
            "label": "GFW cells",
            "value": f"{len(gfw):,}",
            "hint": "fishing effort layer",
            "tone": "info",
        },
    ]
)

tab_map, tab_tracks, tab_ports, tab_anom, tab_gfw, tab_ops = st.tabs(
    [
        "Interactive map",
        "AIS tracks",
        "Port calls (Mombasa)",
        "Anomalies & risk",
        "GFW layers",
        "Ops / refresh",
    ]
)

mmsi_options: list[str] = []
if not vessels.empty and "mmsi" in vessels.columns:
    mmsi_options = vessels["mmsi"].astype(str).tolist()

# ---- MAP ----
with tab_map:
    st.markdown("#### Interactive vessel track map")
    st.caption(
        "Folium map · AIS positions · optional track polyline · GFW effort · "
        "Mombasa approaches · geofences. Green = moving, grey = dwell, amber = loiter/dark, red = high risk."
    )
    c1, c2 = st.columns([3, 1])
    with c1:
        selected_map = st.selectbox(
            "Highlight / load track for MMSI",
            options=["—"] + mmsi_options[:400],
            key="map_mmsi",
        )
    with c2:
        st.write("")
        st.write("")
        load_track = selected_map != "—"

    sel = None if selected_map == "—" else selected_map
    track_preview = svc.vessel_track(sel, hours=track_hours) if sel else pd.DataFrame()

    if not HAS_FOLIUM:
        banner(
            "Map library missing",
            "Install folium + streamlit-folium to enable the interactive map.",
            tone="warning",
        )
    else:
        fmap = _build_map(
            vessels=vessels if show_anoms else vessels.drop(columns=["risk_flags"], errors="ignore"),
            track=track_preview,
            geofences=snap.geofences,
            gfw=gfw,
            port_events=port_act,
            selected_mmsi=sel,
            show_gfw=show_gfw,
            show_ports=show_ports,
        )
        st_folium(fmap, width=None, height=560, returned_objects=[])

    if vessels.empty:
        banner(
            "No vessels in this window",
            "Run `python ingestion/run_vessel_tracking.py` (seeds sample AIS if empty) "
            "or `python ingestion/fetch_ais_realtime.py` for live AISStream data.",
            tone="warning",
        )
    else:
        st.markdown("##### Fleet snapshot")
        show_cols = [
            c
            for c in (
                "mmsi",
                "vessel_name",
                "vessel_type",
                "flag",
                "lat",
                "lon",
                "sog",
                "cog",
                "last_seen",
                "risk_flags",
                "risk_score",
                "behaviour_level",
                "in_kenya_box",
                "in_kenya_eez",
            )
            if c in vessels.columns
        ]
        st.dataframe(
            vessels[show_cols] if show_cols else vessels,
            width="stretch",
            hide_index=True,
            height=280,
        )

# ---- TRACKS ----
with tab_tracks:
    st.markdown("#### Historical & near real-time AIS tracks")
    default_mmsi = mmsi_options[0] if mmsi_options else ""
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        mmsi_in = st.text_input("MMSI", value=default_mmsi, key="track_mmsi_in")
    with c2:
        st.write("")
        st.write("")
        go = st.button("Load track", type="primary")
    with c3:
        st.metric("Track window", f"{track_hours}h")

    if (go or mmsi_in) and str(mmsi_in).strip():
        mmsi = str(mmsi_in).strip()
        profile = svc.vessel_profile(mmsi)
        track = svc.vessel_track(mmsi, hours=track_hours)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("MMSI", mmsi)
        m2.metric("Name", str(profile.get("vessel_name") or "—")[:28])
        m3.metric("Type / flag", f"{profile.get('vessel_type') or '—'} / {profile.get('flag') or '—'}")
        m4.metric("Points", f"{len(track):,}")

        if track.empty:
            st.warning("No track points for this MMSI in the selected window.")
        else:
            if HAS_FOLIUM:
                st_folium(
                    _build_map(
                        vessels=pd.DataFrame(),
                        track=track,
                        geofences=snap.geofences,
                        gfw=None,
                        port_events=None,
                        selected_mmsi=mmsi,
                        show_gfw=False,
                        show_ports=False,
                    ),
                    width=None,
                    height=420,
                    returned_objects=[],
                )
            if "sog" in track.columns and "ts" in track.columns:
                chart_df = track[["ts", "sog"]].dropna().set_index("ts")
                if not chart_df.empty:
                    st.markdown("##### Speed profile (SOG)")
                    st.line_chart(chart_df, height=200)
            st.dataframe(track.tail(300), width="stretch", hide_index=True)
            st.download_button(
                "Download track CSV",
                data=track.to_csv(index=False).encode("utf-8"),
                file_name=f"ais_track_{mmsi}.csv",
                mime="text/csv",
            )

    if snap.tracks_meta is not None and not snap.tracks_meta.empty:
        st.markdown("##### Track coverage (all MMSIs)")
        st.dataframe(snap.tracks_meta.head(100), width="stretch", hide_index=True)

# ---- PORTS ----
with tab_ports:
    st.markdown("#### Mombasa port arrivals / departures")
    st.caption(
        "Prefer `fact_port_activity` / `fact_port_metrics`. "
        "If empty, arrivals are inferred from AIS inside the Mombasa approaches box."
    )

    if not port_met.empty:
        st.markdown("##### Daily port metrics")
        # time series
        dcol = next((c for c in ("metric_date", "date") if c in port_met.columns), None)
        arr_c = next(
            (c for c in ("arrivals", "arrival_count") if c in port_met.columns),
            None,
        )
        dep_c = next(
            (c for c in ("departures", "departure_count") if c in port_met.columns),
            None,
        )
        if dcol and (arr_c or dep_c):
            ts = port_met.set_index(dcol)
            cols = [c for c in (arr_c, dep_c, "active_vessels", "congestion_index") if c and c in ts.columns]
            if cols:
                st.line_chart(ts[cols], height=240)
        st.dataframe(port_met.tail(30), width="stretch", hide_index=True)
    else:
        st.info(
            "No `fact_port_metrics` yet. Seed with "
            "`python ingestion/seed_port_activity.py` for Mombasa daily series."
        )

    st.markdown("##### Recent port events")
    if port_act.empty:
        st.warning("No port events in window.")
    else:
        # simple daily counts if event_time present
        if "event_time" in port_act.columns and "event_type" in port_act.columns:
            tmp = port_act.copy()
            tmp["day"] = pd.to_datetime(tmp["event_time"], errors="coerce").dt.date
            tmp["event_type"] = tmp["event_type"].astype(str).str.upper()
            pivot = (
                tmp.groupby(["day", "event_type"])
                .size()
                .unstack(fill_value=0)
                .sort_index()
            )
            if not pivot.empty:
                st.bar_chart(pivot, height=220)
        st.dataframe(port_act.head(200), width="stretch", hide_index=True)
        st.download_button(
            "Download port events CSV",
            data=port_act.to_csv(index=False).encode("utf-8"),
            file_name="mombasa_port_events.csv",
            mime="text/csv",
        )

# ---- ANOMALIES ----
with tab_anom:
    st.markdown("#### Anomaly detection — loitering, dark cues, unusual routes")
    st.caption(
        "Flags combine behaviour scores, low-speed ratio, MPA interaction, "
        "missing identity + dwell (dark cue), and optional `fact_vessel_anomalies`."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Fleet risk flags")
        if vessels.empty or "risk_flags" not in vessels.columns:
            st.info("No fleet rows to flag.")
        else:
            flagged = vessels[
                vessels["risk_flags"].astype(str).str.upper().ne("OK")
            ].copy()
            show = [
                c
                for c in (
                    "mmsi",
                    "vessel_name",
                    "vessel_type",
                    "flag",
                    "sog",
                    "risk_flags",
                    "risk_score",
                    "behaviour_score",
                    "low_speed_ratio",
                    "last_seen",
                )
                if c in flagged.columns
            ]
            st.dataframe(
                flagged[show] if show else flagged,
                width="stretch",
                hide_index=True,
                height=320,
            )
    with c2:
        st.markdown("##### Behaviour scores")
        if beh.empty:
            st.info("No behaviour rows — profiles still carry risk on the map.")
        else:
            st.dataframe(beh.head(100), width="stretch", hide_index=True, height=320)

    st.markdown("##### ML / rule anomalies table")
    if anom.empty:
        st.info(
            "Optional: `python ingestion/run_vessel_tracking.py --anomalies` "
            "writes `fact_vessel_anomalies`."
        )
    else:
        st.dataframe(anom.head(200), width="stretch", hide_index=True)

    if not vessels.empty and "risk_flags" in vessels.columns:
        st.markdown("##### Flag mix")
        # explode simple tokens
        tokens: list[str] = []
        for v in vessels["risk_flags"].astype(str):
            if v.upper() == "OK":
                tokens.append("OK")
            else:
                tokens.extend([t.strip() for t in v.replace("·", "|").split("|") if t.strip()])
        if tokens:
            st.bar_chart(pd.Series(tokens).value_counts())

# ---- GFW ----
with tab_gfw:
    st.markdown("#### Global Fishing Watch data layers")
    st.caption(
        "Effort cells from `fact_gfw_fishing_effort` or `fact_fishing_effort` "
        "clipped to the Kenya / WIO box. Overlay also available on the map tab."
    )
    if gfw.empty:
        st.info(
            "No GFW rows in warehouse yet. "
            "Populate via GFW ingest / `python ingestion/seed_ais_sample.py` (light effort) "
            "or the GFW fishing effort job."
        )
    else:
        glat, glon = _lat_lon(gfw)
        st.metric("Cells in view", f"{len(gfw):,}")
        st.dataframe(gfw.head(300), width="stretch", hide_index=True)
        if HAS_FOLIUM and glat and glon:
            st_folium(
                _build_map(
                    vessels=pd.DataFrame(),
                    track=None,
                    geofences=snap.geofences,
                    gfw=gfw,
                    port_events=None,
                    selected_mmsi=None,
                    show_gfw=True,
                    show_ports=False,
                ),
                width=None,
                height=420,
                returned_objects=[],
            )
        st.caption(
            "GFW layers are decision-support only — not a legal determination of fishing activity."
        )

# ---- OPS ----
with tab_ops:
    st.markdown("#### How this page is fed")
    st.markdown(
        """
| Feature | Source |
|---------|--------|
| AIS positions / tracks | `fact_ais_positions`, `fact_vessel_track_points` |
| Vessel profiles / risk | `fact_vessel_profiles`, behaviour scores |
| Geofences | `dim_geofences`, `fact_geofence_events` |
| Mombasa port calls | `fact_port_activity`, `fact_port_metrics` (else AIS heuristic) |
| GFW effort | `fact_gfw_fishing_effort` / `fact_fishing_effort` |
| Anomalies | profile flags + optional `fact_vessel_anomalies` |
"""
    )
    st.code(
        "\n".join(
            [
                "# Full vessel tracking rebuild (auto-seeds AIS if empty)",
                "python ingestion/run_vessel_tracking.py",
                "",
                "# Mombasa port arrivals / daily metrics",
                "python ingestion/seed_port_activity.py",
                "",
                "# Live AIS (AISSTREAM_API_KEY required)",
                "python ingestion/fetch_ais_realtime.py",
                "",
                "# Optional ML anomalies",
                "python ingestion/run_vessel_tracking.py --anomalies",
            ]
        ),
        language="bash",
    )
    st.markdown(
        """
**Planned features — status**

| Capability | Status |
|------------|--------|
| Interactive vessel track map (Folium) | **Live** |
| Filter by vessel type, flag, speed | **Live** |
| Historical + near real-time AIS tracks | **Live** |
| Mombasa arrivals / departures + time-series | **Live** (seed port job if empty) |
| Risk / anomaly flags (loiter, dark cue, high risk) | **Live** |
| Global Fishing Watch layers | **Live** when GFW tables populated |
| Kepler.gl | Optional later — Folium covers ops map today |
"""
    )

close_page()

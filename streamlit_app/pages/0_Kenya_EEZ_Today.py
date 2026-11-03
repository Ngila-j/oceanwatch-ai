"""Kenya EEZ Today — Phase 11 complete ops view."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from components.data_access import has_error, qdf_or_error
from components.pagekit import banner, boot, close_page, kpi_row
from components.ui import section

boot(
    "Kenya EEZ Today",
    "Complete ops snapshot for Kenya’s exclusive economic zone — "
    "spatial risk, coastal tides, swim windows, events, and provenance.",
    kicker="Kenya EEZ · Phase 11",
    chips=(
        ("Domain", "primary"),
        ("Tides & swim", "info"),
        ("Live warehouse", "success"),
    ),
    icon="🇰🇪",
)

if st.button("Refresh Kenya EEZ", type="primary", use_container_width=False):
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=120, show_spinner="Loading Kenya EEZ…")
def _load_bundle() -> dict[str, pd.DataFrame]:
    return {
        "fresh": qdf_or_error(
            "SELECT * FROM data_freshness ORDER BY source_key"
        ),
        "spatial": qdf_or_error(
            """
            SELECT * FROM spatial_intelligence
            ORDER BY as_of DESC NULLS LAST, risk_score DESC NULLS LAST
            LIMIT 200
            """
        ),
        "events": qdf_or_error(
            """
            SELECT * FROM oceanwatch_events
            ORDER BY COALESCE(detected_at, created_at) DESC NULLS LAST
            LIMIT 300
            """
        ),
        "risks": qdf_or_error(
            """
            SELECT * FROM risk_scores
            ORDER BY as_of DESC NULLS LAST, risk_score DESC NULLS LAST
            LIMIT 200
            """
        ),
        "prov": qdf_or_error(
            "SELECT * FROM data_provenance ORDER BY dataset_key"
        ),
        "ocean": qdf_or_error(
            """
            SELECT * FROM fact_ocean_conditions
            ORDER BY 1 DESC
            LIMIT 50
            """
        ),
        "ports": qdf_or_error(
            """
            SELECT * FROM fact_port_metrics
            ORDER BY 1 DESC
            LIMIT 50
            """
        ),
        "wio": qdf_or_error(
            """
            SELECT * FROM fact_wio_intelligence_index
            ORDER BY index_date DESC NULLS LAST
            LIMIT 14
            """
        ),
        "stations": qdf_or_error(
            """
            SELECT * FROM fact_coastal_stations
            ORDER BY station_name
            """
        ),
        "tides": qdf_or_error(
            """
            SELECT * FROM fact_tide_heights
            WHERE ts_utc >= NOW() - INTERVAL '6 hours'
              AND ts_utc <= NOW() + INTERVAL '72 hours'
            ORDER BY ts_utc
            LIMIT 5000
            """
        ),
        "swim": qdf_or_error(
            """
            SELECT w.*, s.station_name, s.zone_id, s.lat, s.lon
            FROM fact_swim_windows w
            LEFT JOIN fact_coastal_stations s ON s.station_id = w.station_id
            WHERE w.window_date >= CURRENT_DATE - 1
            ORDER BY w.window_date, s.station_name
            LIMIT 200
            """
        ),
        "tide_now": qdf_or_error(
            """
            SELECT DISTINCT ON (t.station_id)
              t.station_id, s.station_name, s.zone_id, s.lat, s.lon,
              t.ts_utc, t.tide_height_m, t.tide_rate_m_per_h, t.stage,
              t.swim_rating, t.swim_reason, t.is_daylight
            FROM fact_tide_heights t
            LEFT JOIN fact_coastal_stations s ON s.station_id = t.station_id
            WHERE t.ts_utc <= NOW() + INTERVAL '30 minutes'
            ORDER BY t.station_id, t.ts_utc DESC
            """
        ),
    }


def _ok(df: pd.DataFrame) -> bool:
    return df is not None and not df.empty and not has_error(df)


def _err(df: pd.DataFrame) -> str | None:
    if df is not None and has_error(df):
        try:
            return str(df["error"].iloc[0])
        except Exception:  # noqa: BLE001
            return "query error"
    return None


data = _load_bundle()
fresh = data["fresh"]
spatial = data["spatial"]
events = data["events"]
risks = data["risks"]
prov = data["prov"]
ocean = data["ocean"]
ports = data["ports"]
wio = data["wio"]
stations = data["stations"]
tides = data["tides"]
swim = data["swim"]
tide_now = data["tide_now"]

missing = []
for label, frame in (
    ("data_freshness", fresh),
    ("spatial_intelligence", spatial),
    ("oceanwatch_events", events),
    ("risk_scores", risks),
    ("data_provenance", prov),
):
    err = _err(frame)
    if err and any(
        t in err.lower()
        for t in ("does not exist", "undefinedtable", "relation", "undefined table")
    ):
        missing.append(label)

if missing:
    banner(
        "Kenya EEZ tables not ready",
        "Initialise Phase 11, then refresh.\n\n"
        "`python ingestion/init_phase11_complete.py`\n"
        "`python ingestion/run_phase11_intelligence.py`\n\n"
        f"Missing: {', '.join(missing)}",
        tone="warning",
        icon="⚠️",
    )
    with st.expander("Diagnostics"):
        for label, frame in (
            ("fresh", fresh),
            ("spatial", spatial),
            ("events", events),
            ("risks", risks),
            ("prov", prov),
        ):
            e = _err(frame)
            if e:
                st.code(f"{label}: {e}")
    close_page()
    st.stop()

# ── KPIs ────────────────────────────────────────────────────────────────────
open_events = 0
if _ok(events):
    sc = next((c for c in events.columns if c.lower() == "status"), None)
    if sc:
        open_events = int(
            events[sc].astype(str).str.upper().isin({"OPEN", "NEW", "ACTIVE"}).sum()
        )
    else:
        open_events = len(events)

high_zones = 0
if _ok(spatial):
    tc = next((c for c in spatial.columns if c.lower() == "risk_tier"), None)
    if tc:
        high_zones = int(
            spatial[tc]
            .astype(str)
            .str.upper()
            .isin({"HIGH", "CRITICAL"})
            .sum()
        )

fresh_ok = 0
fresh_n = 0
if _ok(fresh):
    fresh_n = len(fresh)
    sc = next((c for c in fresh.columns if c.lower() == "status"), None)
    if sc:
        fresh_ok = int(
            fresh[sc].astype(str).str.upper().isin({"OK", "DAILY_OK", "FRESH"}).sum()
        )

avg_risk = "—"
if _ok(risks):
    rc = next((c for c in risks.columns if c.lower() == "risk_score"), None)
    if rc is not None:
        try:
            avg_risk = f"{float(pd.to_numeric(risks[rc], errors='coerce').mean()):.0f}"
        except Exception:  # noqa: BLE001
            avg_risk = "—"

wio_score = "—"
if _ok(wio):
    oc = next(
        (c for c in wio.columns if c.lower() in ("overall_score", "score", "index_value")),
        None,
    )
    if oc is not None:
        try:
            wio_score = f"{float(pd.to_numeric(wio[oc], errors='coerce').iloc[0]):.0f}"
        except Exception:  # noqa: BLE001
            wio_score = "—"

fav_now = 0
tide_stations_n = 0
if _ok(tide_now):
    tide_stations_n = len(tide_now)
    rc = next((c for c in tide_now.columns if c.lower() == "swim_rating"), None)
    if rc:
        fav_now = int(
            tide_now[rc].astype(str).str.upper().eq("FAVOURABLE").sum()
        )

kpi_row(
    [
        {
            "label": "Open events",
            "value": f"{open_events:,}",
            "hint": "oceanwatch_events",
            "tone": "danger" if open_events >= 5 else "primary",
        },
        {
            "label": "High-risk zones",
            "value": f"{high_zones:,}",
            "hint": "spatial_intelligence",
            "tone": "warning" if high_zones else "success",
        },
        {
            "label": "Swim-favourable now",
            "value": f"{fav_now}/{tide_stations_n}" if tide_stations_n else "—",
            "hint": "coastal stations this hour",
            "tone": "success" if fav_now else ("warning" if tide_stations_n else "info"),
        },
        {
            "label": "Fresh sources",
            "value": f"{fresh_ok}/{fresh_n}" if fresh_n else "—",
            "hint": "data_freshness OK",
            "tone": "success" if fresh_n and fresh_ok == fresh_n else "info",
        },
        {
            "label": "WIO index",
            "value": str(wio_score),
            "hint": "latest overall",
            "tone": "info",
        },
    ]
)

empty_bits = [
    name
    for name, df in (
        ("spatial", spatial),
        ("events", events),
        ("risks", risks),
        ("freshness", fresh),
        ("provenance", prov),
    )
    if not _ok(df)
]
if empty_bits:
    banner(
        "Some Kenya EEZ panels are empty",
        "Tables exist but have no rows yet: "
        + ", ".join(empty_bits)
        + ".\n\n`python ingestion/run_phase11_intelligence.py`",
        tone="info",
        icon="ℹ️",
    )

tab_sit, tab_tides, tab_evt, tab_risk, tab_fresh, tab_data = st.tabs(
    ["Situation", "Tides & swimming", "Events", "Risk", "Freshness", "Data & ports"]
)

with tab_sit:
    section(
        "Spatial intelligence",
        "Zone-level composite for Kenya EEZ watch boxes.",
    )
    if _ok(spatial):
        # latest as_of only if multiple days
        view = spatial.copy()
        if "as_of" in view.columns:
            try:
                latest = view["as_of"].max()
                view = view[view["as_of"] == latest]
            except Exception:  # noqa: BLE001
                pass
        prefer = [
            c
            for c in (
                "zone_name",
                "zone_id",
                "risk_tier",
                "risk_score",
                "tide_height_m",
                "tide_stage",
                "swim_rating",
                "next_favourable_start",
                "vessel_count",
                "dark_count",
                "fishing_hours",
                "sst_c",
                "bloom_risk",
                "notes",
                "as_of",
            )
            if c in view.columns
        ]
        st.dataframe(
            view[prefer] if prefer else view,
            use_container_width=True,
            hide_index=True,
            height=360,
        )
        if "risk_score" in view.columns and "zone_name" in view.columns:
            chart_df = (
                view[["zone_name", "risk_score"]]
                .dropna()
                .sort_values("risk_score", ascending=False)
                .set_index("zone_name")
            )
            if not chart_df.empty:
                st.bar_chart(chart_df)
    else:
        st.info("No spatial_intelligence rows. Run Phase 11 intelligence.")

with tab_tides:
    section(
        "Coastal tide heights & swim windows",
        "Hourly tide forecast for Kenya coastal stations with recreational "
        "swim ratings (FAVOURABLE / CAUTION / RISKY). Model is harmonic and "
        "indicative — not a substitute for KMFRI tables or local lifeguards.",
    )

    if not _ok(tide_now) and not _ok(tides):
        banner(
            "Tide tables not loaded",
            "Run `python ingestion/run_kenya_coastal_tides.py` then refresh.",
            tone="warning",
            icon="🌊",
        )
    else:
        # Station picker
        stn_opts: list[str] = []
        label_by_id: dict[str, str] = {}
        if _ok(stations):
            for _, r in stations.iterrows():
                sid = str(r.get("station_id", ""))
                name = str(r.get("station_name", sid))
                label_by_id[sid] = name
                stn_opts.append(sid)
        elif _ok(tide_now) and "station_id" in tide_now.columns:
            stn_opts = sorted(tide_now["station_id"].astype(str).unique().tolist())
            for sid in stn_opts:
                label_by_id[sid] = sid

        pick_labels = [f"{label_by_id.get(s, s)} ({s})" for s in stn_opts]
        c_a, c_b = st.columns([2, 1])
        with c_a:
            chosen_label = st.selectbox(
                "Coastal station",
                pick_labels,
                index=0 if pick_labels else None,
            )
        chosen_id = stn_opts[pick_labels.index(chosen_label)] if pick_labels else None
        with c_b:
            horizon = st.slider("Forecast hours", 12, 72, 36, step=6)

        # Now strip across stations
        if _ok(tide_now):
            section("Right now — all stations", "Current hour height and swim rating.")
            now_view = tide_now.copy()
            prefer_now = [
                c
                for c in (
                    "station_name",
                    "zone_id",
                    "ts_utc",
                    "tide_height_m",
                    "stage",
                    "tide_rate_m_per_h",
                    "swim_rating",
                    "swim_reason",
                    "is_daylight",
                )
                if c in now_view.columns
            ]
            st.dataframe(
                now_view[prefer_now] if prefer_now else now_view,
                use_container_width=True,
                hide_index=True,
                height=280,
            )
            # quick KPI for selection
            if chosen_id and "station_id" in now_view.columns:
                row = now_view[now_view["station_id"].astype(str) == chosen_id]
                if not row.empty:
                    r0 = row.iloc[0]
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric(
                        "Tide height",
                        f"{float(r0.get('tide_height_m', float('nan'))):.2f} m",
                    )
                    k2.metric("Stage", str(r0.get("stage", "—")))
                    k3.metric("Swim", str(r0.get("swim_rating", "—")))
                    rate = r0.get("tide_rate_m_per_h")
                    k4.metric(
                        "Rate",
                        f"{float(rate):+.2f} m/h" if rate is not None else "—",
                    )
                    reason = r0.get("swim_reason")
                    if reason:
                        st.caption(str(reason))

        # Chart + table for selected station
        if chosen_id and _ok(tides) and "station_id" in tides.columns:
            series = tides[tides["station_id"].astype(str) == str(chosen_id)].copy()
            if "ts_utc" in series.columns:
                series = series.sort_values("ts_utc")
                try:
                    cutoff = pd.Timestamp.utcnow() + pd.Timedelta(hours=int(horizon))
                    # handle tz-aware/naive
                    ts = pd.to_datetime(series["ts_utc"], utc=True)
                    series = series.assign(_ts=ts)
                    series = series[series["_ts"] <= cutoff]
                except Exception:  # noqa: BLE001
                    series = series.head(horizon)

            if not series.empty and "tide_height_m" in series.columns:
                chart = series.set_index(
                    "ts_utc" if "ts_utc" in series.columns else series.index
                )[["tide_height_m"]]
                st.line_chart(chart)

            # colour-ish table of hours
            prefer_t = [
                c
                for c in (
                    "ts_utc",
                    "tide_height_m",
                    "stage",
                    "tide_rate_m_per_h",
                    "swim_rating",
                    "swim_reason",
                    "is_daylight",
                )
                if c in series.columns
            ]
            st.dataframe(
                series[prefer_t] if prefer_t else series,
                use_container_width=True,
                hide_index=True,
                height=360,
            )

            # favourable hours list (daylight)
            if "swim_rating" in series.columns:
                fav_hours = series[
                    series["swim_rating"].astype(str).str.upper() == "FAVOURABLE"
                ]
                if not fav_hours.empty:
                    st.success(
                        f"**{len(fav_hours)} favourable hour(s)** in the next "
                        f"{horizon}h at {label_by_id.get(chosen_id, chosen_id)}."
                    )
                else:
                    st.warning(
                        "No FAVOURABLE swim hours in this horizon — "
                        "see CAUTION windows and avoid low-tide / strong-stream slots."
                    )

        # Daily rollup
        if _ok(swim):
            section(
                "Daily swim window summary",
                "Favourable / caution / risky hour counts and next HW/LW.",
            )
            sw = swim.copy()
            if chosen_id and "station_id" in sw.columns:
                sw_show = sw[sw["station_id"].astype(str) == str(chosen_id)]
                if sw_show.empty:
                    sw_show = sw
            else:
                sw_show = sw
            prefer_sw = [
                c
                for c in (
                    "window_date",
                    "station_name",
                    "favourable_hours",
                    "caution_hours",
                    "risky_hours",
                    "high_tide_today_m",
                    "high_tide_at",
                    "low_tide_today_m",
                    "low_tide_at",
                    "next_favourable_start",
                    "next_favourable_end",
                    "summary",
                )
                if c in sw_show.columns
            ]
            st.dataframe(
                sw_show[prefer_sw] if prefer_sw else sw_show,
                use_container_width=True,
                hide_index=True,
                height=280,
            )

        if _ok(stations) and {"lat", "lon"}.issubset(set(stations.columns)):
            section("Station map", "Kenya coastal tide / swim stations.")
            m = stations.dropna(subset=["lat", "lon"]).rename(
                columns={"lat": "latitude", "lon": "longitude"}
            )
            if not m.empty:
                st.map(m[["latitude", "longitude"]])

    st.caption(
        "Ratings: **FAVOURABLE** = mid–high tide near slack · "
        "**CAUTION** = transitional or night · "
        "**RISKY** = low tide (reef/rocks) or strong flood/ebb. "
        "Always check local conditions, lifeguards, and weather."
    )

with tab_evt:
    section("Domain events", "Detected cues across the Kenya EEZ.")
    if _ok(events):
        ev = events.copy()
        c1, c2, c3 = st.columns(3)
        sev_col = next((c for c in ev.columns if c.lower() == "severity"), None)
        type_col = next((c for c in ev.columns if c.lower() == "event_type"), None)
        status_col = next((c for c in ev.columns if c.lower() == "status"), None)
        with c1:
            sev_opts = (
                sorted(ev[sev_col].dropna().astype(str).unique()) if sev_col else []
            )
            sev_sel = st.multiselect("Severity", sev_opts, default=[])
        with c2:
            type_opts = (
                sorted(ev[type_col].dropna().astype(str).unique()) if type_col else []
            )
            type_sel = st.multiselect("Type", type_opts, default=[])
        with c3:
            st_opts = (
                sorted(ev[status_col].dropna().astype(str).unique())
                if status_col
                else []
            )
            st_sel = st.multiselect("Status", st_opts, default=[])
        if sev_col and sev_sel:
            ev = ev[ev[sev_col].astype(str).isin(sev_sel)]
        if type_col and type_sel:
            ev = ev[ev[type_col].astype(str).isin(type_sel)]
        if status_col and st_sel:
            ev = ev[ev[status_col].astype(str).isin(st_sel)]

        prefer = [
            c
            for c in (
                "detected_at",
                "severity",
                "event_type",
                "title",
                "status",
                "risk_score",
                "region_id",
                "lat",
                "lon",
                "event_id",
            )
            if c in ev.columns
        ]
        st.dataframe(
            ev[prefer] if prefer else ev,
            use_container_width=True,
            hide_index=True,
            height=380,
        )
        if {"lat", "lon"}.issubset(set(ev.columns)):
            m = ev.dropna(subset=["lat", "lon"])
            if not m.empty:
                st.map(m.rename(columns={"lat": "latitude", "lon": "longitude"})[
                    ["latitude", "longitude"]
                ])
    else:
        st.info("No oceanwatch_events rows yet.")

with tab_risk:
    section("Entity risk scores", "Zones, ports, corridors, and fleet composites.")
    if _ok(risks):
        prefer = [
            c
            for c in (
                "entity_type",
                "entity_id",
                "risk_tier",
                "risk_score",
                "drivers",
                "as_of",
                "computed_at",
            )
            if c in risks.columns
        ]
        st.dataframe(
            risks[prefer] if prefer else risks,
            use_container_width=True,
            hide_index=True,
            height=360,
        )
        if "risk_tier" in risks.columns:
            tier_counts = (
                risks["risk_tier"].astype(str).value_counts().rename_axis("tier").reset_index(name="n")
            )
            st.bar_chart(tier_counts.set_index("tier"))
    else:
        st.info("No risk_scores rows yet.")

    if _ok(wio):
        section("WIO intelligence index", "Latest regional composite.")
        st.dataframe(wio, use_container_width=True, hide_index=True)
        try:
            drivers = wio.iloc[0].get("drivers")
            if drivers:
                st.caption("Drivers")
                if isinstance(drivers, str):
                    try:
                        st.json(json.loads(drivers))
                    except Exception:  # noqa: BLE001
                        st.write(drivers)
                else:
                    st.write(drivers)
        except Exception:  # noqa: BLE001
            pass

with tab_fresh:
    section("Pipeline freshness", "Age and status of upstream sources.")
    if _ok(fresh):
        prefer = [
            c
            for c in (
                "source_name",
                "source_key",
                "status",
                "age_minutes",
                "expected_cadence",
                "last_success_at",
                "notes",
            )
            if c in fresh.columns
        ]
        st.dataframe(
            fresh[prefer] if prefer else fresh,
            use_container_width=True,
            hide_index=True,
            height=360,
        )
    else:
        st.info("No data_freshness rows.")

    section("Provenance", "Who provides each dataset and on what terms.")
    if _ok(prov):
        st.dataframe(prov, use_container_width=True, hide_index=True, height=320)
    else:
        st.info("No data_provenance rows.")

with tab_data:
    section("Ocean conditions", "Recent SST / ocean rows for the EEZ.")
    if _ok(ocean):
        st.dataframe(ocean, use_container_width=True, hide_index=True, height=280)
    else:
        st.info(
            "fact_ocean_conditions empty — run ocean ingest or Phase 11 seed fallback."
        )

    section("Port metrics", "Mombasa / Lamu style port snapshots.")
    if _ok(ports):
        st.dataframe(ports, use_container_width=True, hide_index=True, height=280)
    else:
        st.info("fact_port_metrics empty — run port metrics job or Phase 11 seed.")

banner(
    "Ops note",
    "Kenya EEZ Today reads Phase 11 warehouse tables. Re-run "
    "`python ingestion/run_phase11_intelligence.py` after AIS/ocean/port jobs "
    "and `python ingestion/run_kenya_coastal_tides.py` for tide/swim windows. "
    "Tide heights are harmonic forecasts for ops planning — verify against "
    "KMFRI / official tables for safety-critical use.",
    tone="info",
    icon="ℹ️",
)

close_page()

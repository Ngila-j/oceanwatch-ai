"""Port Intelligence — Mombasa (Phase 14 + extended analytics)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from components.pagekit import boot, close_page  # noqa: E402
from components.ui import banner, kpi_row  # noqa: E402
from services.port_intelligence import PortIntelligenceService  # noqa: E402

try:
    import plotly.express as px
    import plotly.graph_objects as go

    HAS_PX = True
except ImportError:
    HAS_PX = False

boot(
    "Port Intelligence — Mombasa",
    "Command center · forecasts · berth pressure · vessel mix · AIS near-port · what-if",
    chips=[("Phase 14", "primary"), ("Mombasa", "info"), ("Live analytics", "success")],
)


@st.cache_resource(show_spinner=False)
def _svc() -> PortIntelligenceService:
    return PortIntelligenceService()


@st.cache_data(ttl=120, show_spinner=False)
def _load_bundle():
    return _svc().load_bundle(activity_limit=400)


svc = _svc()
with st.spinner("Loading Mombasa port intelligence…"):
    bundle = _load_bundle()

# Sidebar controls
with st.sidebar:
    st.markdown("### Port controls")
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Cache TTL ~2 min")
    ais_hours = st.slider("AIS near-port window (h)", 6, 168, 48, 6)
    show_map = st.toggle("Show AIS map", value=True)

if not bundle.has_any:
    banner(
        "No Phase 14 data",
        "Warehouse has no port tables yet, or the app cannot reach the DB.",
        tone="warning",
    )
    if bundle.errors:
        with st.expander("Connection / query errors"):
            for e in bundle.errors[:8]:
                st.code(e)
    st.code(
        "\n".join(
            [
                "python ingestion/init_phase14_port.py",
                "python ingestion/seed_port_activity.py",
                "python ingestion/run_phase14_port.py",
            ]
        ),
        language="bash",
    )
    close_page()
    st.stop()

if not bundle.has_phase14:
    banner(
        "Base metrics only",
        "Run `python ingestion/run_phase14_port.py` for forecasts, berth pressure, and ops risk.",
        tone="warning",
    )

k = svc.kpis(bundle)
alerts = svc.watchlist_alerts(bundle)
series = svc.series_frame(bundle)
scorecard = svc.efficiency_scorecard(bundle)
cmp7 = svc.period_compare(bundle, 7)
brief = svc.executive_brief(bundle)

# ---- Top KPIs ----
kpi_row(
    [
        {
            "label": "Performance",
            "value": f"{k.get('performance_score', 0):.0f}",
            "hint": str(k.get("metric_date") or ""),
            "tone": "primary",
        },
        {
            "label": "Congestion",
            "value": f"{k.get('congestion_index', 0):.0f}",
            "hint": k.get("congestion_level") or "",
            "tone": "warning" if (k.get("congestion_index") or 0) >= 55 else "info",
        },
        {
            "label": "Berth pressure",
            "value": f"{k.get('pressure_index', 0):.0f}",
            "hint": k.get("pressure_level") or "",
            "tone": "danger"
            if str(k.get("pressure_level") or "").upper() in ("HIGH", "CRITICAL")
            else "info",
        },
        {
            "label": "Ops risk",
            "value": f"{k.get('ops_risk', 0):.0f}",
            "hint": k.get("ops_level") or "",
            "tone": "danger"
            if str(k.get("ops_level") or "").upper() == "HIGH"
            else "warning"
            if str(k.get("ops_level") or "").upper() == "MODERATE"
            else "success",
        },
        {
            "label": "Arrivals / day",
            "value": f"{int(k.get('arrivals') or 0)}",
            "hint": f"dep {int(k.get('departures') or 0)} · wait {k.get('avg_waiting_hours', 0):.1f}h",
            "tone": "info",
        },
    ]
)

# Executive brief + alerts strip
st.markdown("#### Command brief")
st.markdown(brief)

crit = alerts[alerts["severity"].isin(["CRITICAL", "HIGH"])] if not alerts.empty else alerts
if not crit.empty:
    banner(
        f"{len(crit)} elevated alert(s)",
        " · ".join(crit["message"].astype(str).head(3).tolist()),
        tone="danger" if (crit["severity"] == "CRITICAL").any() else "warning",
    )

(
    tab_cmd,
    tab_perf,
    tab_fc,
    tab_berth,
    tab_mix,
    tab_act,
    tab_ais,
    tab_kpa,
    tab_whatif,
    tab_export,
) = st.tabs(
    [
        "Command center",
        "Performance & trends",
        "Forecasts",
        "Berth & ops risk",
        "Vessel mix & flags",
        "Activity & turnaround",
        "AIS near-port",
        "KPA 14-day list",
        "What-if simulator",
        "Export & jobs",
    ]
)

# ========== COMMAND ==========
with tab_cmd:
    c1, c2 = st.columns((1.2, 1))
    with c1:
        st.markdown("##### Efficiency scorecard")
        if scorecard.empty:
            st.info("No scorecard inputs.")
        else:
            if HAS_PX:
                fig = px.bar(
                    scorecard,
                    x="pillar",
                    y="score",
                    color="score",
                    color_continuous_scale="Tealgrn",
                    range_y=[0, 100],
                    hover_data=["detail", "wow_pct"],
                    title="Operational pillars (0–100)",
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.bar_chart(scorecard.set_index("pillar")["score"])
            st.dataframe(scorecard, width="stretch", hide_index=True)

        st.markdown("##### Week-over-week")
        if cmp7.empty:
            st.caption("Need more history for WoW compare.")
        else:
            st.dataframe(cmp7, width="stretch", hide_index=True)

    with c2:
        st.markdown("##### Watchlist")
        if alerts.empty:
            st.success("No alerts.")
        else:
            def _tone(sev: str) -> str:
                return {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "WATCH": "🟡",
                    "INFO": "🟢",
                }.get(str(sev).upper(), "⚪")

            show = alerts.copy()
            show.insert(0, " ", show["severity"].map(_tone))
            st.dataframe(
                show[[" ", "severity", "code", "message", "value"]],
                width="stretch",
                hide_index=True,
            )

        wait = svc.wait_distribution(bundle)
        st.markdown("##### Wait-time profile")
        if not wait:
            st.caption("No waiting_hours samples.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Mean", f"{wait['mean']:.1f}h")
            m2.metric("P50", f"{wait['p50']:.1f}h")
            m3.metric("P90", f"{wait['p90']:.1f}h")
            m4.metric("Max", f"{wait['max']:.1f}h")

        st.markdown("##### Outlook snapshot")
        o1, o2 = st.columns(2)
        o1.metric(
            "Peak congestion (7d fc)",
            f"{k.get('peak_congestion_fc', float('nan')):.0f}"
            if k.get("peak_congestion_fc") is not None
            else "—",
            help="Max predicted congestion index over forecast horizon",
        )
        o2.metric(
            "Peak arrivals (7d fc)",
            f"{k.get('peak_arrivals_fc', float('nan')):.1f}"
            if k.get("peak_arrivals_fc") is not None
            else "—",
        )

# ========== PERFORMANCE ==========
with tab_perf:
    st.markdown("#### Daily performance, congestion & throughput")
    if series.empty:
        st.info("No series.")
    else:
        ycols = [
            c
            for c in (
                "performance_score",
                "congestion_index",
                "cong_ma7",
                "avg_waiting_hours",
                "wait_ma7",
            )
            if c in series.columns
        ]
        if HAS_PX and ycols:
            fig = px.line(
                series,
                x="metric_date",
                y=ycols,
                title="Scores & congestion (with 7d MA where available)",
            )
            st.plotly_chart(fig, width="stretch")
        elif ycols:
            st.line_chart(series.set_index("metric_date")[ycols])

        bar_cols = [c for c in ("arrivals", "departures") if c in series.columns]
        if HAS_PX and bar_cols:
            st.plotly_chart(
                px.bar(
                    series.tail(28),
                    x="metric_date",
                    y=bar_cols,
                    barmode="group",
                    title="Arrivals vs departures (28d)",
                ),
                width="stretch",
            )
        elif bar_cols:
            st.bar_chart(series.set_index("metric_date")[bar_cols].tail(28))

        st.markdown("##### Weekday profile")
        wd = svc.weekday_profile(bundle)
        if wd.empty:
            st.caption("Not enough dates for weekday profile.")
        else:
            if HAS_PX and "arrivals" in wd.columns:
                fig = px.bar(
                    wd,
                    x="weekday",
                    y=[c for c in ("arrivals", "departures", "congestion_index") if c in wd.columns],
                    barmode="group",
                    title="Average by weekday",
                )
                st.plotly_chart(fig, width="stretch")
            st.dataframe(wd.drop(columns=["dow"], errors="ignore"), width="stretch", hide_index=True)

        st.dataframe(series.tail(30), width="stretch", hide_index=True)

# ========== FORECASTS ==========
with tab_fc:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Congestion forecast (7d)")
        fc = bundle.congestion_fc
        if fc.empty:
            st.info("No congestion forecast — run Phase 14.")
        else:
            if HAS_PX:
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=fc["horizon_day"],
                        y=fc["congestion_index_pred"],
                        mode="lines+markers",
                        name="pred",
                    )
                )
                if "lo" in fc.columns and "hi" in fc.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=list(fc["horizon_day"]) + list(fc["horizon_day"][::-1]),
                            y=list(fc["hi"]) + list(fc["lo"][::-1]),
                            fill="toself",
                            name="band",
                            line=dict(width=0),
                            fillcolor="rgba(0,150,200,0.15)",
                        )
                    )
                fig.update_layout(title="Congestion index forecast", xaxis_title="Horizon day")
                st.plotly_chart(fig, width="stretch")
            else:
                st.line_chart(fc.set_index("horizon_day")[["congestion_index_pred"]])
            st.dataframe(fc, width="stretch", hide_index=True)
    with c2:
        st.markdown("##### Arrival forecast (7d)")
        af = bundle.arrival_fc
        if af.empty:
            st.info("No arrival forecast — run Phase 14.")
        else:
            if HAS_PX:
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(x=af["horizon_day"], y=af["arrivals_pred"], name="arrivals_pred")
                )
                if "lo" in af.columns and "hi" in af.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=af["horizon_day"],
                            y=af["hi"],
                            mode="lines",
                            name="hi",
                            line=dict(dash="dot"),
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=af["horizon_day"],
                            y=af["lo"],
                            mode="lines",
                            name="lo",
                            line=dict(dash="dot"),
                        )
                    )
                fig.update_layout(title="Predicted arrivals", xaxis_title="Horizon day")
                st.plotly_chart(fig, width="stretch")
            else:
                st.bar_chart(af.set_index("horizon_day")[["arrivals_pred"]])
            st.dataframe(af, width="stretch", hide_index=True)

    st.caption("Forecasts are statistical decision-support estimates — not official KPA projections.")

# ========== BERTH & OPS ==========
with tab_berth:
    left, right = st.columns(2)
    with left:
        st.markdown("##### Berth / anchorage pressure")
        if bundle.berth.empty:
            st.info("No berth pressure snapshot.")
        else:
            b0 = bundle.berth.iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Occupancy", f"{float(b0.get('occupancy_pct') or 0):.0f}%")
            m2.metric("Pressure", f"{float(b0.get('pressure_index') or 0):.0f}", str(b0.get("pressure_level") or ""))
            m3.metric("Active", f"{int(b0.get('active_vessels') or 0)}")
            m4.metric("Capacity proxy", f"{int(b0.get('capacity_proxy') or 0)}")
            if HAS_PX:
                fig = go.Figure(
                    go.Indicator(
                        mode="gauge+number",
                        value=float(b0.get("pressure_index") or 0),
                        title={"text": "Berth pressure"},
                        gauge={
                            "axis": {"range": [0, 100]},
                            "bar": {"color": "#0E9AA7"},
                            "steps": [
                                {"range": [0, 35], "color": "#d4edda"},
                                {"range": [35, 55], "color": "#fff3cd"},
                                {"range": [55, 75], "color": "#f8d7da"},
                                {"range": [75, 100], "color": "#f5c6cb"},
                            ],
                            "threshold": {
                                "line": {"color": "red", "width": 2},
                                "value": 75,
                            },
                        },
                    )
                )
                st.plotly_chart(fig, width="stretch")
            st.dataframe(bundle.berth, width="stretch", hide_index=True)
            st.caption("Capacity proxy is a planning assumption — not an official berth count.")

    with right:
        st.markdown("##### Operational risk composite")
        if bundle.ops_risk.empty:
            st.info("No ops risk rows.")
        else:
            o = bundle.ops_risk.iloc[0]
            st.metric(
                "Composite ops risk",
                f"{float(o.get('composite_ops_risk') or 0):.0f}",
                str(o.get("risk_level") or ""),
            )
            comps = {
                "Congestion": float(o.get("congestion_component") or 0),
                "Berth": float(o.get("berth_component") or 0),
                "Wait": float(o.get("wait_component") or 0),
                "Balance": float(o.get("balance_component") or 0),
                "Vessel risk": float(o.get("anomaly_component") or 0),
            }
            if HAS_PX:
                fig = px.bar(
                    x=list(comps.keys()),
                    y=list(comps.values()),
                    labels={"x": "Component", "y": "Score"},
                    title="Risk components",
                    color=list(comps.values()),
                    color_continuous_scale="YlOrRd",
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.bar_chart(pd.Series(comps))
            if o.get("drivers"):
                st.info(f"Drivers: {o['drivers']}")
            st.dataframe(bundle.ops_risk, width="stretch", hide_index=True)

# ========== MIX ==========
with tab_mix:
    mix = svc.vessel_mix(bundle)
    flags = svc.flag_mix(bundle)
    et = svc.event_type_mix(bundle)
    a, b, c = st.columns(3)
    with a:
        st.markdown("##### Vessel mix")
        daily = mix[mix["source"] == "daily_metrics"] if not mix.empty and "source" in mix.columns else mix
        if daily.empty:
            st.caption("No vessel-type breakdown on latest day.")
        elif HAS_PX:
            st.plotly_chart(
                px.pie(daily, names="category", values="count", title="Latest day fleet mix"),
                width="stretch",
            )
        else:
            st.dataframe(daily, width="stretch", hide_index=True)
    with b:
        st.markdown("##### Activity vessel types")
        act_mix = mix[mix["source"] == "activity_events"] if not mix.empty and "source" in mix.columns else pd.DataFrame()
        if act_mix.empty:
            st.caption("No activity vessel_type field.")
        elif HAS_PX:
            st.plotly_chart(
                px.bar(act_mix.head(10), x="category", y="count", title="Event vessel types"),
                width="stretch",
            )
        else:
            st.dataframe(act_mix, width="stretch", hide_index=True)
    with c:
        st.markdown("##### Flag / registry mix")
        if flags.empty:
            st.caption("No flag column on activity.")
        elif HAS_PX:
            st.plotly_chart(
                px.bar(flags.head(12), x="flag", y="events", title="Flags by event count"),
                width="stretch",
            )
        else:
            st.dataframe(flags.head(12), width="stretch", hide_index=True)

    if not et.empty:
        st.markdown("##### Event types")
        if HAS_PX:
            st.plotly_chart(px.pie(et, names="event_type", values="count"), width="stretch")
        st.dataframe(et, width="stretch", hide_index=True)

# ========== ACTIVITY ==========
with tab_act:
    st.markdown("#### Port activity events")
    act = bundle.activity
    if act.empty:
        st.info("No fact_port_activity — run seed_port_activity.py")
    else:
        # filters
        f1, f2, f3 = st.columns(3)
        types = sorted(act["event_type"].dropna().astype(str).unique()) if "event_type" in act.columns else []
        flags_u = sorted(act["flag"].dropna().astype(str).unique()) if "flag" in act.columns else []
        sel_types = f1.multiselect("Event type", types, default=types[:6] if types else [])
        sel_flags = f2.multiselect("Flag", flags_u, default=[])
        q = f3.text_input("Search name / MMSI", "")
        view = act.copy()
        if sel_types and "event_type" in view.columns:
            view = view[view["event_type"].astype(str).isin(sel_types)]
        if sel_flags and "flag" in view.columns:
            view = view[view["flag"].astype(str).isin(sel_flags)]
        if q:
            mask = pd.Series(False, index=view.index)
            for col in ("vessel_name", "mmsi", "vessel_type"):
                if col in view.columns:
                    mask = mask | view[col].astype(str).str.contains(q, case=False, na=False)
            view = view[mask]
        st.caption(f"{len(view)} events after filters")
        st.dataframe(view, width="stretch", hide_index=True)

    st.markdown("##### Turnaround / dwell proxy")
    tt = svc.turnaround_proxy(bundle)
    if tt.empty:
        st.caption("Need dwell_hours on events or paired arrival/departure MMSI rows.")
    else:
        src = str(tt["source"].iloc[0]) if "source" in tt.columns else "proxy"
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Samples", f"{len(tt)}")
        m2.metric("Median dwell", f"{tt['turnaround_hours'].median():.1f}h")
        m3.metric("P90 dwell", f"{tt['turnaround_hours'].quantile(0.9):.1f}h")
        m4.metric("Source", src.replace("_", " ")[:18])
        if HAS_PX:
            color = "vessel_type" if "vessel_type" in tt.columns else None
            st.plotly_chart(
                px.histogram(
                    tt,
                    x="turnaround_hours",
                    color=color,
                    nbins=20,
                    title="Dwell / turnaround hours",
                ),
                width="stretch",
            )
            if color:
                by_type = (
                    tt.groupby(tt["vessel_type"].astype(str).str.upper())["turnaround_hours"]
                    .median()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                by_type.columns = ["vessel_type", "median_dwell_h"]
                st.plotly_chart(
                    px.bar(by_type, x="vessel_type", y="median_dwell_h", title="Median dwell by type"),
                    width="stretch",
                )
        st.dataframe(tt.head(80), width="stretch", hide_index=True)

# ========== AIS ==========
with tab_ais:
    st.markdown(f"#### AIS positions near Mombasa (~{18} nm, last {ais_hours}h)")
    with st.spinner("Querying near-port AIS…"):
        ais = svc.near_port_ais(hours=ais_hours, limit=500)
    if ais.empty:
        st.info(
            "No AIS positions in the Mombasa watch box (or `fact_ais_positions` missing). "
            "Seed/fetch AIS then refresh."
        )
    else:
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Unique vessels", f"{ais['mmsi'].nunique() if 'mmsi' in ais.columns else len(ais)}")
        a2.metric("Samples", f"{len(ais)}")
        if "sog" in ais.columns:
            moving = int((pd.to_numeric(ais["sog"], errors="coerce").fillna(0) >= 1.0).sum())
            a3.metric("Moving (SOG≥1)", f"{moving}")
        if "dist_nm" in ais.columns:
            a4.metric("Median dist", f"{ais['dist_nm'].median():.1f} nm")
        if show_map and {"lat", "lon"}.issubset(ais.columns):
            mp = ais.rename(columns={"lat": "latitude", "lon": "longitude"})
            st.map(mp[["latitude", "longitude"]].dropna(), zoom=9)
            if HAS_PX:
                hover = [c for c in ("vessel_name", "mmsi", "sog", "dist_nm", "vessel_type") if c in ais.columns]
                fig = px.scatter_mapbox(
                    ais,
                    lat="lat",
                    lon="lon",
                    color="dist_nm" if "dist_nm" in ais.columns else None,
                    hover_data=hover or None,
                    zoom=9,
                    height=420,
                    title="Near-port AIS",
                )
                fig.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig, width="stretch")
        st.dataframe(ais.head(200), width="stretch", hide_index=True)

# ========== KPA 14-day ==========
with tab_kpa:
    st.markdown("#### KPA 14-day shipping movement")
    st.caption(
        "Upload the official Word list from [KPA Shipping Movement](https://kpa.co.ke/ShippingMovement). "
        "Stored as OceanWatch decision-support — not an official KPA publication."
    )
    try:
        from services.kpa_shipping import KPAShippingService

        kpa_svc = KPAShippingService(engine=svc.engine if hasattr(svc, "engine") else None)
        ks = kpa_svc.summary()
        k1, k2, k3 = st.columns(3)
        k1.metric("Report date", ks.get("report_date") or "—")
        k2.metric("Vessels", f"{ks.get('vessels') or 0}")
        k3.metric("Rows", f"{ks.get('rows') or 0}")

        up = st.file_uploader("Upload KPA 14-day .docx", type=["docx"], key="port_kpa_docx")
        if up is not None and st.button("Ingest KPA list", key="port_kpa_go", type="primary"):
            with st.spinner("Parsing DOCX…"):
                try:
                    res = kpa_svc.ingest_upload(up.getvalue(), up.name)
                    st.success(f"Loaded {res.get('rows')} rows · report_date={res.get('report_date')}")
                    st.cache_data.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

        kpa_df = kpa_svc.movements(limit=400)
        if kpa_df.empty:
            st.info(
                "No KPA rows yet. Download the latest 14 DAYS LIST from KPA and upload here, "
                "or use **Live Feeds & KPA List** in the sidebar."
            )
            st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Open Live Feeds & KPA →")
            st.page_link("pages/40_Port_Ops_Board.py", label="Open Port Ops Board →")
        else:
            cols = [
                c
                for c in (
                    "report_date",
                    "vessel_name",
                    "voyage",
                    "agent",
                    "eta",
                    "etd",
                    "berth",
                    "cargo",
                    "flag",
                    "origin",
                    "destination",
                )
                if c in kpa_df.columns
            ]
            st.dataframe(kpa_df[cols] if cols else kpa_df, width="stretch", hide_index=True)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"KPA module unavailable: {exc}")

# ========== WHAT-IF ==========
with tab_whatif:
    st.markdown("#### What-if planning simulator")
    st.caption(
        "Sensitivity layer on the latest snapshot — for ops planning discussions, not a berth allocator."
    )
    w1, w2, w3 = st.columns(3)
    extra = w1.slider("Extra arrivals (vs latest day)", -10.0, 15.0, 0.0, 0.5)
    cap_d = w2.slider("Capacity change (berths proxy)", -10.0, 15.0, 0.0, 1.0)
    wait_s = w3.slider("Wait-time shock (hours)", -6.0, 18.0, 0.0, 0.5)
    result = svc.whatif(bundle, extra_arrivals=extra, capacity_delta=cap_d, wait_shock_h=wait_s)
    base, sim, delta = result["base"], result["sim"], result["delta"]

    st.markdown("##### Base → simulated")
    cols = st.columns(5)
    cols[0].metric("Arrivals", f"{sim['arrivals']:.1f}", f"{sim['arrivals'] - base['arrivals']:+.1f}")
    cols[1].metric(
        "Congestion",
        f"{sim['congestion']:.0f}",
        f"{delta['congestion']:+.1f} · {sim['congestion_level']}",
    )
    cols[2].metric(
        "Berth pressure",
        f"{sim['pressure']:.0f}",
        f"{delta['pressure']:+.1f} · {sim['pressure_level']}",
    )
    cols[3].metric("Wait (h)", f"{sim['wait_h']:.1f}", f"{delta['wait_h']:+.1f}")
    cols[4].metric("Performance", f"{sim['performance']:.0f}", f"{delta['performance']:+.1f}")

    if HAS_PX:
        cmp = pd.DataFrame(
            {
                "metric": ["Congestion", "Pressure", "Wait h", "Performance", "Occupancy %"],
                "Base": [
                    base["congestion"],
                    base["pressure"],
                    base["wait_h"],
                    base["performance"],
                    min(160.0, 100.0 * base["active"] / max(1.0, base["capacity"])),
                ],
                "Simulated": [
                    sim["congestion"],
                    sim["pressure"],
                    sim["wait_h"],
                    sim["performance"],
                    sim["occupancy_pct"],
                ],
            }
        )
        melt = cmp.melt(id_vars="metric", var_name="case", value_name="value")
        st.plotly_chart(
            px.bar(melt, x="metric", y="value", color="case", barmode="group", title="Base vs simulated"),
            width="stretch",
        )

    # Preset scenarios
    st.markdown("##### Preset shocks")
    p1, p2, p3 = st.columns(3)
    if p1.button("Arrival surge +8", use_container_width=True):
        st.session_state["_preset"] = (8.0, 0.0, 2.0)
    if p2.button("Berth outage −5 capacity", use_container_width=True):
        st.session_state["_preset"] = (0.0, -5.0, 3.0)
    if p3.button("Smooth day −4 arrivals", use_container_width=True):
        st.session_state["_preset"] = (-4.0, 0.0, -2.0)
    if "_preset" in st.session_state:
        pe, pc, pw = st.session_state["_preset"]
        pr = svc.whatif(bundle, extra_arrivals=pe, capacity_delta=pc, wait_shock_h=pw)
        st.write(
            f"Preset → congestion **{pr['sim']['congestion']:.0f}** "
            f"({pr['delta']['congestion']:+.1f}), pressure **{pr['sim']['pressure']:.0f}**, "
            f"performance **{pr['sim']['performance']:.0f}**"
        )

# ========== EXPORT ==========
with tab_export:
    st.markdown("#### Data pack & rebuild jobs")
    pack = svc.export_pack(bundle)
    # Excel-like multi CSV zip via single combined download options
    for name, df in pack.items():
        if df is None or df.empty:
            continue
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            f"Download {name}.csv",
            data=csv,
            file_name=f"mombasa_{name}.csv",
            mime="text/csv",
            key=f"dl_{name}",
        )

    # One-shot workbook if openpyxl/xlsxwriter available — fallback buffer of CSVs
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            for name, df in pack.items():
                if df is None or df.empty:
                    continue
                sheet = name[:31]
                df.to_excel(writer, sheet_name=sheet, index=False)
        st.download_button(
            "Download full Excel pack",
            data=buf.getvalue(),
            file_name="mombasa_port_intelligence.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception:
        st.caption("Install `xlsxwriter` for multi-sheet Excel export (CSV buttons still work).")

    st.markdown("##### Rebuild Phase 14")
    st.code(
        "\n".join(
            [
                "python ingestion/init_phase14_port.py",
                "python ingestion/seed_port_activity.py",
                "python ingestion/run_phase14_port.py",
            ]
        ),
        language="bash",
    )
    st.markdown(
        """
| Table / layer | Role |
|---------------|------|
| `fact_port_metrics` | Daily arrivals / congestion base |
| `fact_port_performance` | Scored daily performance |
| `fact_port_congestion_forecast` | 7-day congestion outlook |
| `fact_port_arrival_forecast` | 7-day arrival outlook |
| `fact_berth_pressure` | Occupancy / pressure snapshot |
| `fact_port_ops_risk` | Composite operational risk |
| `fact_port_activity` | Event-level arrivals/departures |
| `fact_ais_positions` | Near-port AIS context |
"""
    )
    if bundle.errors:
        with st.expander("Query warnings"):
            for e in bundle.errors[:10]:
                st.code(e)
    st.caption(
        "OceanWatch decision-support only — not official Kenya Ports Authority figures."
    )

close_page()

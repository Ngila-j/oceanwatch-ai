"""Port Intelligence Advanced — Mombasa deep-dive (uses shared service)."""

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
from services.port_intelligence import PortIntelligenceService  # noqa: E402

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    HAS_PX = True
except ImportError:
    HAS_PX = False

boot(
    "Port Intelligence — Advanced",
    "Deep-dive diagnostics · correlations · multi-horizon stress · data quality",
    chips=[("Phase 14", "primary"), ("Advanced", "info")],
)


@st.cache_resource(show_spinner=False)
def _svc() -> PortIntelligenceService:
    return PortIntelligenceService()


@st.cache_data(ttl=120, show_spinner=False)
def _bundle():
    return _svc().load_bundle(activity_limit=500)


svc = _svc()
bundle = _bundle()

if not bundle.has_any:
    banner("No port data", "Run Phase 14 jobs, then refresh.", tone="warning")
    st.code(
        "python ingestion/init_phase14_port.py\n"
        "python ingestion/seed_port_activity.py\n"
        "python ingestion/run_phase14_port.py",
        language="bash",
    )
    close_page()
    st.stop()

k = svc.kpis(bundle)
series = svc.series_frame(bundle)
alerts = svc.watchlist_alerts(bundle)

kpi_row(
    [
        {
            "label": "Perf",
            "value": f"{k.get('performance_score', 0):.0f}",
            "hint": "score",
            "tone": "primary",
        },
        {
            "label": "Congestion",
            "value": f"{k.get('congestion_index', 0):.0f}",
            "hint": k.get("congestion_level") or "",
            "tone": "warning",
        },
        {
            "label": "Ops risk",
            "value": f"{k.get('ops_risk', 0):.0f}",
            "hint": k.get("ops_level") or "",
            "tone": "danger" if (k.get("ops_risk") or 0) >= 70 else "info",
        },
        {
            "label": "Alerts",
            "value": f"{len(alerts[alerts['severity'].isin(['CRITICAL','HIGH'])]) if not alerts.empty else 0}",
            "hint": "CRITICAL+HIGH",
            "tone": "warning",
        },
    ]
)

st.info(svc.executive_brief(bundle))

t1, t2, t3, t4, t5 = st.tabs(
    [
        "Correlations & drivers",
        "Stress matrix",
        "Forecast diagnostics",
        "Data quality",
        "Raw tables",
    ]
)

with t1:
    st.markdown("#### What moves with congestion?")
    if series.empty or "congestion_index" not in series.columns:
        st.warning("Need congestion series.")
    else:
        cols = [
            c
            for c in (
                "arrivals",
                "departures",
                "active_vessels",
                "avg_waiting_hours",
                "performance_score",
                "throughput_proxy",
                "balance_ratio",
                "container_vessels",
                "tankers",
            )
            if c in series.columns
        ]
        if not cols:
            st.caption("No comparable numeric columns.")
        else:
            corr = (
                series[["congestion_index"] + cols]
                .apply(pd.to_numeric, errors="coerce")
                .corr()["congestion_index"]
                .drop(labels=["congestion_index"], errors="ignore")
                .sort_values(key=lambda s: s.abs(), ascending=False)
            )
            cdf = corr.reset_index()
            cdf.columns = ["feature", "corr_with_congestion"]
            if HAS_PX:
                st.plotly_chart(
                    px.bar(
                        cdf,
                        x="feature",
                        y="corr_with_congestion",
                        color="corr_with_congestion",
                        color_continuous_scale="RdBu_r",
                        title="Correlation with congestion_index",
                    ),
                    width="stretch",
                )
            st.dataframe(cdf, width="stretch", hide_index=True)

            if HAS_PX and "arrivals" in series.columns and "avg_waiting_hours" in series.columns:
                fig = px.scatter(
                    series,
                    x="arrivals",
                    y="avg_waiting_hours",
                    size="congestion_index" if "congestion_index" in series.columns else None,
                    color="congestion_index",
                    hover_data=["metric_date"],
                    title="Arrivals vs wait (size/color = congestion)",
                    color_continuous_scale="YlOrRd",
                )
                st.plotly_chart(fig, width="stretch")

        if HAS_PX and len(cols) >= 2:
            num = series[["congestion_index"] + cols].apply(pd.to_numeric, errors="coerce")
            st.plotly_chart(
                px.imshow(
                    num.corr(),
                    text_auto=".2f",
                    color_continuous_scale="RdBu_r",
                    zmin=-1,
                    zmax=1,
                    title="Correlation heatmap",
                ),
                width="stretch",
            )

with t2:
    st.markdown("#### Arrival × capacity stress matrix")
    st.caption("Grid of what-if congestion outcomes (planning surface).")
    arr_grid = list(range(-6, 13, 3))
    cap_grid = list(range(-6, 10, 3))
    heat = []
    for a in arr_grid:
        row = {"extra_arrivals": a}
        for c in cap_grid:
            r = svc.whatif(bundle, extra_arrivals=float(a), capacity_delta=float(c))
            row[f"cap{c:+d}"] = r["sim"]["congestion"]
        heat.append(row)
    hdf = pd.DataFrame(heat).set_index("extra_arrivals")
    if HAS_PX:
        st.plotly_chart(
            px.imshow(
                hdf.values,
                x=[f"cap {c:+d}" for c in cap_grid],
                y=[f"arr {a:+d}" for a in arr_grid],
                color_continuous_scale="YlOrRd",
                labels=dict(color="cong"),
                text_auto=".0f",
                title="Simulated congestion index",
            ),
            width="stretch",
        )
    st.dataframe(hdf, width="stretch")

    st.markdown("##### Pressure surface (same grid)")
    heat_p = []
    for a in arr_grid:
        row = {"extra_arrivals": a}
        for c in cap_grid:
            r = svc.whatif(bundle, extra_arrivals=float(a), capacity_delta=float(c))
            row[f"cap{c:+d}"] = r["sim"]["pressure"]
        heat_p.append(row)
    st.dataframe(pd.DataFrame(heat_p).set_index("extra_arrivals"), width="stretch")

with t3:
    st.markdown("#### Forecast vs recent actuals")
    if bundle.congestion_fc.empty or series.empty:
        st.info("Need both forecast and history.")
    else:
        last_c = float(series["congestion_index"].iloc[-1]) if "congestion_index" in series.columns else None
        fc = bundle.congestion_fc.copy()
        if last_c is not None and "congestion_index_pred" in fc.columns:
            fc["delta_vs_today"] = fc["congestion_index_pred"] - last_c
        if HAS_PX and "congestion_index_pred" in fc.columns:
            fig = make_subplots(specs=[[{"secondary_y": False}]])
            fig.add_trace(
                go.Scatter(
                    x=series["metric_date"].tail(14),
                    y=series["congestion_index"].tail(14),
                    name="actual",
                    mode="lines+markers",
                )
            )
            # Attach forecast to last date + horizon
            if not series.empty:
                last_d = pd.to_datetime(series["metric_date"].iloc[-1])
                fx = [last_d + pd.Timedelta(days=int(h)) for h in fc["horizon_day"]]
                fig.add_trace(
                    go.Scatter(
                        x=fx,
                        y=fc["congestion_index_pred"],
                        name="forecast",
                        mode="lines+markers",
                        line=dict(dash="dash"),
                    )
                )
            fig.update_layout(title="Congestion: recent actuals + 7d forecast")
            st.plotly_chart(fig, width="stretch")
        st.dataframe(fc, width="stretch", hide_index=True)

    if not bundle.arrival_fc.empty and not series.empty and "arrivals" in series.columns:
        st.markdown("##### Arrival forecast vs 7d average")
        avg7 = float(series["arrivals"].tail(7).mean())
        af = bundle.arrival_fc.copy()
        af["vs_7d_avg"] = af["arrivals_pred"] - avg7
        st.metric("Recent 7d avg arrivals", f"{avg7:.1f}")
        st.dataframe(af, width="stretch", hide_index=True)

with t4:
    st.markdown("#### Coverage & freshness")
    rows = []
    for label, df, ts_candidates in [
        ("performance", bundle.performance, ["metric_date", "created_at"]),
        ("congestion_fc", bundle.congestion_fc, ["forecast_date", "created_at"]),
        ("arrival_fc", bundle.arrival_fc, ["forecast_date", "created_at"]),
        ("berth", bundle.berth, ["as_of", "created_at"]),
        ("ops_risk", bundle.ops_risk, ["as_of", "created_at"]),
        ("metrics", bundle.metrics, ["metric_date", "created_at"]),
        ("activity", bundle.activity, ["event_time", "created_at"]),
    ]:
        fresh = None
        for c in ts_candidates:
            if df is not None and not df.empty and c in df.columns:
                fresh = str(pd.to_datetime(df[c], errors="coerce").max())
                break
        rows.append(
            {
                "layer": label,
                "rows": 0 if df is None else len(df),
                "cols": 0 if df is None or df.empty else len(df.columns),
                "latest_ts": fresh or "—",
                "empty": df is None or df.empty,
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if bundle.errors:
        st.markdown("##### Query errors")
        for e in bundle.errors[:12]:
            st.code(e)

    st.markdown("##### Wait distribution")
    st.json(svc.wait_distribution(bundle) or {"note": "no samples"})

with t5:
    st.markdown("#### Raw warehouse extracts")
    choice = st.selectbox(
        "Table",
        [
            "performance",
            "metrics",
            "congestion_fc",
            "arrival_fc",
            "berth",
            "ops_risk",
            "activity",
            "alerts",
            "scorecard",
            "period_compare",
            "weekday",
            "turnaround",
        ],
    )
    mapping = {
        "performance": bundle.performance,
        "metrics": bundle.metrics,
        "congestion_fc": bundle.congestion_fc,
        "arrival_fc": bundle.arrival_fc,
        "berth": bundle.berth,
        "ops_risk": bundle.ops_risk,
        "activity": bundle.activity,
        "alerts": alerts,
        "scorecard": svc.efficiency_scorecard(bundle),
        "period_compare": svc.period_compare(bundle, 7),
        "weekday": svc.weekday_profile(bundle),
        "turnaround": svc.turnaround_proxy(bundle),
    }
    df = mapping.get(choice, pd.DataFrame())
    st.dataframe(df, width="stretch", hide_index=True)
    if not df.empty:
        st.download_button(
            "CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"mombasa_adv_{choice}.csv",
            mime="text/csv",
        )

st.caption("Advanced diagnostics for OceanWatch planners — not official KPA statistics.")
close_page()

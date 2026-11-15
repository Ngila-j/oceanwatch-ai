"""Live free feeds + KPA 14-day Shipping Movement upload."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from components.pagekit import boot, close_page
from components.ui import empty_state, kpi_row
from services.kpa_shipping import KPAShippingService
from services.live_feeds import LiveFeedsService

boot(
    "Live Feeds & KPA List",
    "Free live weather/marine/earthquake feeds + Kenya Ports Authority 14-day shipping movement upload.",
    chips=[
        ("Free sources", "success"),
        ("KPA DOCX", "primary"),
        ("No paid APIs", "info"),
    ],
)

live = LiveFeedsService()
kpa = KPAShippingService()

tab_live, tab_kpa, tab_ops, tab_catalog = st.tabs(
    ["Live free feeds", "KPA 14-day list", "Ops fusion", "Source catalog"]
)

# ---------- LIVE ----------
with tab_live:
    st.markdown("#### Free live feeds (no account required)")
    st.caption(
        "Open-Meteo weather & marine + USGS earthquakes for Kenya / Western Indian Ocean. "
        "Refresh pulls live HTTP APIs into the warehouse."
    )
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Refresh free feeds now", type="primary", use_container_width=True):
            with st.spinner("Fetching Open-Meteo + USGS…"):
                try:
                    summary = live.refresh_free_feeds()
                    st.success(str(summary))
                    st.cache_data.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Refresh failed: {exc}")

    cards = live.status_cards()
    kpi_row(
        [
            {
                "label": c["title"].split("(")[0].strip(),
                "value": "OK" if c["ok"] else "—",
                "hint": c["detail"],
                "tone": "success" if c["ok"] else "warning",
            }
            for c in cards
        ]
    )

    w = live.latest_weather()
    m = live.latest_marine()
    q = live.earthquakes(40)

    st.markdown("##### Weather snapshot")
    if w.empty:
        empty_state("No weather rows", "Click Refresh free feeds now.", icon="🌤️")
    else:
        st.dataframe(w, width="stretch", hide_index=True)

    st.markdown("##### Marine snapshot (waves / SST)")
    if m.empty:
        empty_state("No marine rows", "Click Refresh free feeds now.", icon="🌊")
    else:
        st.dataframe(m, width="stretch", hide_index=True)
        mom = m[m["location"] == "Mombasa"] if "location" in m.columns else m.head(0)
        if not mom.empty:
            r = mom.iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Mombasa wave m", f"{float(r.get('wave_height_m') or 0):.2f}")
            m2.metric("Swell m", f"{float(r.get('swell_height_m') or 0):.2f}")
            m3.metric("SST °C", f"{float(r.get('sea_temp_c') or 0):.1f}")
            m4.metric("Period s", f"{float(r.get('wave_period_s') or 0):.1f}")

    st.markdown("##### WIO earthquakes (USGS)")
    if q.empty:
        st.caption("No earthquake rows in window (or not fetched yet).")
    else:
        st.dataframe(q, width="stretch", hide_index=True)

    st.markdown("##### Feed run log")
    log = live.run_log(25)
    if not log.empty:
        st.dataframe(log, width="stretch", hide_index=True)

# ---------- KPA ----------
with tab_kpa:
    st.markdown("#### KPA Shipping Movement (14-day list)")
    st.markdown(
        "Download the latest **14 DAYS LIST** `.docx` from "
        "[kpa.co.ke/ShippingMovement](https://kpa.co.ke/ShippingMovement) "
        "or [Fourteen Days List](https://www.kpa.co.ke/FourteenDaysList), then upload here. "
        "OceanWatch stores a decision-support copy — **not** an official KPA publication."
    )

    summary = kpa.summary()
    kpi_row(
        [
            {
                "label": "Report date",
                "value": summary.get("report_date") or "—",
                "hint": "latest ingested",
                "tone": "primary",
            },
            {
                "label": "Vessels",
                "value": str(summary.get("vessels") or 0),
                "hint": f"{summary.get('rows') or 0} rows",
                "tone": "info",
            },
            {
                "label": "Last ingest",
                "value": (summary.get("ingested_at") or "—")[:16],
                "hint": "UTC",
                "tone": "success" if summary.get("rows") else "warning",
            },
        ]
    )

    up = st.file_uploader(
        "Upload KPA 14-day list (.docx)",
        type=["docx"],
        accept_multiple_files=False,
        help="Word document from KPA Shipping Movement page",
    )
    src = st.text_input(
        "Attribution URL",
        value="https://kpa.co.ke/ShippingMovement",
        key="kpa_src_url",
    )
    if up is not None and st.button("Parse & load into warehouse", type="primary"):
        with st.spinner("Parsing DOCX tables…"):
            try:
                result = kpa.ingest_upload(up.getvalue(), up.name, source_url=src)
                st.success(
                    f"Loaded **{result.get('rows')}** rows · report_date={result.get('report_date')} · "
                    f"file={result.get('file')}"
                )
                st.cache_data.clear()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Ingest failed: {exc}")

    mv = kpa.movements(limit=400)
    st.markdown("##### Current warehouse list")
    if mv.empty:
        empty_state(
            "No KPA rows yet",
            "Upload a 14 DAYS LIST .docx from the KPA website.",
            icon="📄",
        )
    else:
        show_cols = [
            c
            for c in [
                "report_date",
                "vessel_name",
                "voyage",
                "agent",
                "eta",
                "etd",
                "berth",
                "cargo",
                "loa_m",
                "draft_m",
                "flag",
                "origin",
                "destination",
                "movement_type",
                "source_file",
            ]
            if c in mv.columns
        ]
        st.dataframe(mv[show_cols] if show_cols else mv, width="stretch", hide_index=True)
        st.download_button(
            "Download CSV",
            data=mv.to_csv(index=False).encode("utf-8"),
            file_name="kpa_shipping_movement.csv",
            mime="text/csv",
        )

    logs = kpa.ingest_logs()
    if not logs.empty:
        with st.expander("Ingest log"):
            st.dataframe(logs, width="stretch", hide_index=True)


# ---------- OPS FUSION ----------
with tab_ops:
    st.markdown("#### Port Ops fusion (KPA + AIS + seas)")
    st.caption("Full interactive board lives on the Port Ops Board page.")
    st.page_link("pages/40_Port_Ops_Board.py", label="Open Port Ops Board — Mombasa →")
    try:
        from services.port_ops_board import PortOpsBoardService

        @st.cache_data(ttl=90, show_spinner=False)
        def _ops_pack():
            return PortOpsBoardService().load_pack()

        op = _ops_pack()
        kpi_row(
            [
                {
                    "label": "KPA vessels",
                    "value": str(op.kpis.get("kpa_vessels") or 0),
                    "hint": str(op.kpis.get("kpa_report_date") or "—"),
                    "tone": "primary",
                },
                {
                    "label": "AIS matches",
                    "value": str(op.kpis.get("matches") or 0),
                    "hint": f"{op.kpis.get('match_rate_pct') or 0}%",
                    "tone": "success",
                },
                {
                    "label": "ETA ≤48h",
                    "value": str(op.kpis.get("arrivals_48h") or 0),
                    "hint": "expected arrivals",
                    "tone": "warning",
                },
                {
                    "label": "Wave m",
                    "value": f"{float(op.kpis['wave_m']):.1f}" if op.kpis.get("wave_m") is not None else "—",
                    "hint": "Mombasa marine",
                    "tone": "info",
                },
            ]
        )
        st.markdown(op.brief)
        if not op.arrival_board.empty:
            st.dataframe(op.arrival_board.head(25), width="stretch", hide_index=True)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Ops board unavailable: {exc}")

# ---------- CATALOG ----------
with tab_catalog:
    st.markdown("#### Free / freemium source catalog")
    st.info(
        "**Accounts & API keys:** third-party sign-up needs your email and acceptance of their terms. "
        "This app cannot create accounts on your behalf. Free no-key feeds are already integrated; "
        "for AISStream / GFW / Copernicus, create a free account, put the key in `ingestion/.env`, "
        "then run the existing fetch jobs."
    )
    cat = pd.DataFrame(live.free_source_catalog())
    st.dataframe(cat, width="stretch", hide_index=True)

    st.markdown("##### Env keys (optional free tiers)")
    st.code(
        """
# ingestion/.env
AISSTREAM_API_KEY=           # https://aisstream.io — free AIS websocket
GFW_API_TOKEN=               # Global Fishing Watch API token
COPERNICUS_USERNAME=
COPERNICUS_PASSWORD=
        """.strip(),
        language="bash",
    )
    st.markdown("##### CLI")
    st.code(
        """
python ingestion/fetch_free_live_feeds.py --init
python ingestion/ingest_kpa_shipping_movement.py --init path/to/14_days_list.docx
python ingestion/fetch_ais_realtime.py   # needs AISSTREAM_API_KEY
        """.strip(),
        language="bash",
    )

close_page()

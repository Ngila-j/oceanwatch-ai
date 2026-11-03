"""
Operator Notebook — session notes that stamp into mission packs.

Lightweight freeform log for watch-floor annotations. Stored in session
state (exportable). Decision-support only.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from components.mission import (
    add_watch_item,
    get_mission_context,
    get_watchlist,
    render_mission_strip,
    render_watchlist_panel,
)
from components.pagekit import boot, close_page
from components.ui import banner

boot(
    "Operator Notebook",
    "Session notes and watch-floor annotations. Export alongside mission packs. "
    "Notes live in this browser session unless you download them.",
    kicker="OceanWatch AI · Ops",
    chips=[("NOTES", "info"), ("SESSION", "neutral")],
    icon="📝",
)

_NOTES_KEY = "ow_operator_notes"

render_mission_strip(get_mission_context())

banner(
    "Session-scoped notebook",
    "Entries are kept in Streamlit session state. Download JSON/Markdown before "
    "closing the browser if you need a durable record.",
    tone="info",
    icon="ℹ️",
)

if _NOTES_KEY not in st.session_state:
    st.session_state[_NOTES_KEY] = []

notes: list = st.session_state[_NOTES_KEY]

c1, c2 = st.columns([2, 1])
with c1:
    st.markdown("### New note")
    title = st.text_input("Title", placeholder="e.g. Dark gap near Lamu")
    body = st.text_area("Body", height=140, placeholder="Observation, source, recommended next step…")
    tags = st.text_input("Tags (comma-separated)", placeholder="ais, dark, port")
    pin = st.checkbox("Also pin title to watchlist as a note", value=False)
    if st.button("Add note", type="primary"):
        if not (title or body).strip():
            st.warning("Add a title or body.")
        else:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "title": (title or "Untitled").strip(),
                "body": (body or "").strip(),
                "tags": [t.strip() for t in (tags or "").split(",") if t.strip()],
                "region": get_mission_context().get("region"),
                "callsign": get_mission_context().get("operator_callsign") or "",
            }
            notes.insert(0, entry)
            st.session_state[_NOTES_KEY] = notes
            if pin:
                add_watch_item(
                    kind="note",
                    key=entry["title"][:64],
                    label=entry["title"],
                    note=entry["body"][:120],
                )
            st.success("Note added.")
            st.rerun()

with c2:
    st.markdown("### Export")
    import json

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mission": get_mission_context(),
        "notes": notes,
        "watchlist": get_watchlist(),
    }
    st.download_button(
        "Download notebook (.json)",
        data=json.dumps(payload, indent=2, default=str).encode("utf-8"),
        file_name="oceanwatch_operator_notebook.json",
        mime="application/json",
        use_container_width=True,
    )
    md_lines = [
        "# OceanWatch Operator Notebook",
        f"_UTC {payload['generated_at']}_",
        f"Region: **{payload['mission'].get('region')}**",
        "",
    ]
    for n in notes:
        md_lines.append(f"## {n.get('title')}")
        md_lines.append(f"*{n.get('ts')}* · tags: {', '.join(n.get('tags') or [])}")
        md_lines.append("")
        md_lines.append(n.get("body") or "")
        md_lines.append("")
    st.download_button(
        "Download notebook (.md)",
        data="\n".join(md_lines).encode("utf-8"),
        file_name="oceanwatch_operator_notebook.md",
        mime="text/markdown",
        use_container_width=True,
    )
    if st.button("Clear all notes", use_container_width=True) and notes:
        st.session_state[_NOTES_KEY] = []
        st.rerun()

st.markdown("---")
st.markdown("### Notes log")
if not notes:
    st.info("No notes yet — capture an observation above.")
else:
    for i, n in enumerate(notes):
        with st.expander(f"{n.get('title')} · {str(n.get('ts', ''))[:19]}", expanded=i == 0):
            st.write(n.get("body") or "_empty_")
            if n.get("tags"):
                st.caption("Tags: " + ", ".join(n["tags"]))
            st.caption(
                f"Region {n.get('region')} · {n.get('callsign') or 'no callsign'}"
            )
            if st.button("Delete", key=f"del_note_{i}"):
                notes.pop(i)
                st.session_state[_NOTES_KEY] = notes
                st.rerun()

st.markdown("---")
render_watchlist_panel(editable=True, key_prefix="nb_wl")

close_page(methodology=True, attribution=True)

"""
OceanWatch visual theme
Light data canvas + deep navy navigation (not full dark mode).
"""

import streamlit as st

# Palette
BG_APP = "#F4F7FA"          # main canvas
BG_SIDEBAR = "#0B1F33"      # deep navy sidebar
BG_HEADER = "#071A2D"       # darker navy header band
BG_CARD = "#FFFFFF"         # panels
PRIMARY = "#1677C8"         # ocean blue
SECONDARY = "#16A6A0"       # teal
TEXT_MAIN = "#1A2332"
TEXT_MUTED = "#5B6B7C"
SIDEBAR_TEXT = "#E8EEF5"
SIDEBAR_MUTED = "#9BB0C3"
BORDER = "#D7E0EA"


def apply() -> None:
    st.markdown(
        f"""
<style>
/* ----- App canvas ----- */
html, body, [data-testid="stAppViewContainer"] {{
  background-color: {BG_APP} !important;
  color: {TEXT_MAIN};
}}
[data-testid="stHeader"] {{
  background: {BG_HEADER} !important;
}}
[data-testid="stToolbar"] {{
  background: {BG_HEADER} !important;
}}

/* Main block */
.block-container {{
  padding-top: 1.25rem;
  padding-bottom: 2rem;
  max-width: 1400px;
}}

/* ----- Sidebar (deep navy) ----- */
[data-testid="stSidebar"] {{
  background-color: {BG_SIDEBAR} !important;
}}
[data-testid="stSidebar"] * {{
  color: {SIDEBAR_TEXT} !important;
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] label {{
  color: {SIDEBAR_MUTED} !important;
}}
[data-testid="stSidebar"] hr {{
  border-color: rgba(255,255,255,0.12) !important;
}}

/* Active / hover nav */
[data-testid="stSidebar"] a:hover,
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {{
  background-color: rgba(22, 119, 200, 0.25) !important;
}}
[data-testid="stSidebar"] [aria-selected="true"],
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{
  background-color: rgba(22, 119, 200, 0.35) !important;
  border-left: 3px solid {PRIMARY} !important;
}}

/* Section headers in sidebar */
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {{
  color: {SIDEBAR_MUTED} !important;
}}

/* ----- Typography ----- */
h1, h2, h3 {{
  color: {TEXT_MAIN} !important;
  letter-spacing: -0.02em;
}}
[data-testid="stCaption"] {{
  color: {TEXT_MUTED} !important;
}}

/* ----- Metrics as soft cards ----- */
[data-testid="stMetric"] {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 12px;
  padding: 0.75rem 1rem;
  box-shadow: 0 1px 2px rgba(11, 31, 51, 0.04);
}}
[data-testid="stMetricLabel"] {{
  color: {TEXT_MUTED} !important;
}}
[data-testid="stMetricValue"] {{
  color: {TEXT_MAIN} !important;
}}

/* ----- Expanders / containers feel like cards ----- */
[data-testid="stExpander"] {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 12px;
}}

/* Buttons */
.stButton > button {{
  background-color: {PRIMARY} !important;
  color: white !important;
  border: none !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}}
.stButton > button:hover {{
  background-color: #1266AD !important;
  color: white !important;
}}

/* Secondary-looking links */
a {{
  color: {PRIMARY} !important;
}}

/* Info / success / warning boxes */
[data-testid="stAlert"] {{
  border-radius: 10px;
}}

/* Dataframes */
[data-testid="stDataFrame"] {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 10px;
}}

/* Tabs */
button[data-baseweb="tab"] {{
  color: {TEXT_MUTED} !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
  color: {PRIMARY} !important;
  border-bottom-color: {PRIMARY} !important;
}}

/* Accent utility for custom HTML if needed */
.ow-accent {{ color: {PRIMARY}; }}
.ow-teal {{ color: {SECONDARY}; }}
.ow-card {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}}
</style>
        """,
        unsafe_allow_html=True,
    )
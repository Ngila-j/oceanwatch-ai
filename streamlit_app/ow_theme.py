"""
OceanWatch design system
========================
Light-first maritime cockpit with deep navy chrome.
Accessibility: skip link, focus rings, reduced motion, high contrast,
large type, dark mode, screen-reader utilities, keyboard-friendly targets.
"""

from __future__ import annotations

import streamlit as st

# ── Design tokens ──────────────────────────────────────────────────────────
BG_APP = "#F5F7FA"
BG_SIDEBAR = "#0B1F33"
BG_CARD = "#FFFFFF"
BG_MUTED = "#EEF2F6"
BORDER = "#D7E0EA"
BORDER_STRONG = "#B6C5D6"

TEXT = "#0F172A"
TEXT_SECONDARY = "#475569"
TEXT_MUTED = "#64748B"
TEXT_ON_DARK = "#E8EEF5"
TEXT_ON_DARK_MUTED = "#9FB0C3"

PRIMARY = "#0B6E99"
PRIMARY_HOVER = "#095A7D"
PRIMARY_SOFT = "#E6F3F9"
ACCENT = "#0D9488"
ACCENT_SOFT = "#E6F7F5"

SUCCESS = "#047857"
SUCCESS_BG = "#ECFDF5"
WARNING = "#B45309"
WARNING_BG = "#FFFBEB"
DANGER = "#B91C1C"
DANGER_BG = "#FEF2F2"
INFO = "#1D4ED8"
INFO_BG = "#EFF6FF"

FOCUS_RING = "#2563EB"
FOCUS_OUTLINE = "0 0 0 3px rgba(37, 99, 235, 0.45)"

FONT_STACK = (
    '"IBM Plex Sans", "Source Sans 3", "Segoe UI", system-ui, -apple-system, '
    '"Helvetica Neue", Arial, sans-serif'
)
MONO_STACK = '"IBM Plex Mono", "Cascadia Code", "Consolas", ui-monospace, monospace'

# Plotly defaults (shared)
PLOTLY_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": FONT_STACK, "color": TEXT, "size": 13},
    "margin": {"l": 40, "r": 24, "t": 48, "b": 40},
    "colorway": [
        PRIMARY,
        ACCENT,
        "#7C3AED",
        "#DB2777",
        "#EA580C",
        "#0891B2",
        SUCCESS,
        WARNING,
    ],
    "xaxis": {
        "gridcolor": "#E2E8F0",
        "zerolinecolor": "#CBD5E1",
        "linecolor": "#CBD5E1",
        "tickfont": {"color": TEXT_SECONDARY},
        "title": {"font": {"color": TEXT_SECONDARY}},
    },
    "yaxis": {
        "gridcolor": "#E2E8F0",
        "zerolinecolor": "#CBD5E1",
        "linecolor": "#CBD5E1",
        "tickfont": {"color": TEXT_SECONDARY},
        "title": {"font": {"color": TEXT_SECONDARY}},
    },
    "legend": {
        "bgcolor": "rgba(255,255,255,0.85)",
        "bordercolor": BORDER,
        "borderwidth": 1,
        "font": {"color": TEXT},
    },
}


def _a11y_flags() -> dict:
    return {
        "high_contrast": bool(st.session_state.get("a11y_high_contrast", False)),
        "large_text": bool(st.session_state.get("a11y_large_text", False)),
        "reduced_motion": bool(st.session_state.get("a11y_reduced_motion", False)),
        "dark_mode": bool(st.session_state.get("a11y_dark_mode", False)),
        "underline_links": bool(st.session_state.get("a11y_underline_links", True)),
    }


def init_a11y_defaults() -> None:
    """Seed accessibility prefs once per session."""
    defaults = {
        "a11y_high_contrast": False,
        "a11y_large_text": False,
        "a11y_reduced_motion": False,
        "a11y_dark_mode": False,
        "a11y_underline_links": True,
        "low_bandwidth": False,
        "compact_nav": False,
        "persona": "Analyst",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_theme() -> None:
    """Inject global CSS design system + accessibility layers."""
    init_a11y_defaults()
    flags = _a11y_flags()

    root_mods = []
    body_classes = []
    if flags["high_contrast"]:
        body_classes.append("ow-hc")
        root_mods.append("--ow-border: #0F172A;")
        root_mods.append("--ow-text: #000000;")
        root_mods.append("--ow-text-secondary: #111827;")
        root_mods.append("--ow-primary: #005F8A;")
        root_mods.append("--ow-focus: #0000EE;")
    if flags["large_text"]:
        body_classes.append("ow-lg")
        root_mods.append("--ow-base-size: 18px;")
        root_mods.append("--ow-line: 1.65;")
    if flags["reduced_motion"]:
        body_classes.append("ow-rm")
    if flags["dark_mode"]:
        body_classes.append("ow-dark")
    if flags["underline_links"]:
        body_classes.append("ow-ul")

    root_extra = "\n            ".join(root_mods)
    cls_attr = " ".join(body_classes)

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {{
  --ow-bg: {BG_APP};
  --ow-sidebar: {BG_SIDEBAR};
  --ow-card: {BG_CARD};
  --ow-muted: {BG_MUTED};
  --ow-border: {BORDER};
  --ow-border-strong: {BORDER_STRONG};
  --ow-text: {TEXT};
  --ow-text-secondary: {TEXT_SECONDARY};
  --ow-text-muted: {TEXT_MUTED};
  --ow-on-dark: {TEXT_ON_DARK};
  --ow-on-dark-muted: {TEXT_ON_DARK_MUTED};
  --ow-primary: {PRIMARY};
  --ow-primary-hover: {PRIMARY_HOVER};
  --ow-primary-soft: {PRIMARY_SOFT};
  --ow-accent: {ACCENT};
  --ow-success: {SUCCESS};
  --ow-success-bg: {SUCCESS_BG};
  --ow-warning: {WARNING};
  --ow-warning-bg: {WARNING_BG};
  --ow-danger: {DANGER};
  --ow-danger-bg: {DANGER_BG};
  --ow-info: {INFO};
  --ow-info-bg: {INFO_BG};
  --ow-focus: {FOCUS_RING};
  --ow-radius: 12px;
  --ow-radius-sm: 8px;
  --ow-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 8px 24px rgba(15, 23, 42, 0.06);
  --ow-shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
  --ow-base-size: 15px;
  --ow-line: 1.55;
  --ow-space: 1rem;
  --ow-font: {FONT_STACK};
  --ow-mono: {MONO_STACK};
  {root_extra}
}}

/* Dark mode token override */
.ow-dark, .ow-dark [data-testid="stAppViewContainer"],
body.ow-dark {{
  --ow-bg: #0B1220;
  --ow-card: #111827;
  --ow-muted: #1E293B;
  --ow-border: #334155;
  --ow-border-strong: #475569;
  --ow-text: #F1F5F9;
  --ow-text-secondary: #CBD5E1;
  --ow-text-muted: #94A3B8;
  --ow-primary: #38BDF8;
  --ow-primary-hover: #7DD3FC;
  --ow-primary-soft: #0C4A6E;
  --ow-success-bg: #064E3B;
  --ow-warning-bg: #78350F;
  --ow-danger-bg: #7F1D1D;
  --ow-info-bg: #1E3A8A;
  --ow-shadow: 0 1px 2px rgba(0,0,0,0.35), 0 12px 32px rgba(0,0,0,0.35);
}}

html, body, [data-testid="stAppViewContainer"], .stApp {{
  font-family: var(--ow-font) !important;
  font-size: var(--ow-base-size) !important;
  line-height: var(--ow-line) !important;
  color: var(--ow-text) !important;
  background: var(--ow-bg) !important;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}

/* Skip link — visible on keyboard focus */
.ow-skip {{
  position: absolute;
  left: 12px;
  top: -100px;
  z-index: 10000;
  background: var(--ow-primary);
  color: #fff !important;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  text-decoration: none !important;
  box-shadow: var(--ow-shadow);
}}
.ow-skip:focus {{
  top: 12px;
  outline: 3px solid #fff;
  outline-offset: 2px;
}}

/* Main canvas */
[data-testid="stAppViewContainer"] > .main {{
  background: var(--ow-bg);
}}
.main .block-container {{
  padding-top: 1.25rem !important;
  padding-bottom: 3rem !important;
  max-width: 1280px;
}}

/* Sidebar chrome */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #0B1F33 0%, #0A1828 100%) !important;
  border-right: 1px solid rgba(255,255,255,0.06);
}}
[data-testid="stSidebar"] * {{
  color: var(--ow-on-dark) !important;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown {{
  color: var(--ow-on-dark) !important;
}}
[data-testid="stSidebarNav"] a {{
  border-radius: 8px !important;
  margin: 2px 6px !important;
  padding: 0.45rem 0.7rem !important;
  min-height: 40px;
  transition: background 0.15s ease;
}}
[data-testid="stSidebarNav"] a:hover {{
  background: rgba(255,255,255,0.08) !important;
}}
[data-testid="stSidebarNav"] a:focus-visible {{
  outline: 2px solid #7DD3FC !important;
  outline-offset: 2px !important;
}}
[data-testid="stSidebarNav"] [aria-selected="true"],
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: rgba(56, 189, 248, 0.18) !important;
  box-shadow: inset 3px 0 0 #38BDF8;
  font-weight: 600 !important;
}}
[data-testid="stSidebarNav"] small,
[data-testid="stSidebarNav"] span[data-testid="stSidebarNavSeparator"] {{
  color: var(--ow-on-dark-muted) !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
}}

/* Brand block in sidebar */
.ow-brand {{
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.35rem 0.25rem 0.85rem;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 0.75rem;
}}
.ow-brand-mark {{
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0B6E99, #0D9488);
  display: grid;
  place-items: center;
  font-weight: 700;
  color: #fff;
  font-size: 0.95rem;
  letter-spacing: -0.02em;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(11, 110, 153, 0.35);
}}
.ow-brand-title {{
  font-weight: 700;
  font-size: 1.05rem;
  line-height: 1.2;
  color: #F8FAFC !important;
  margin: 0;
}}
.ow-brand-sub {{
  margin: 0.1rem 0 0;
  font-size: 0.78rem;
  color: #9FB0C3 !important;
  line-height: 1.35;
}}

/* Page header */
.ow-page-header {{
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin: 0 0 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--ow-border);
}}
.ow-page-kicker {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ow-primary);
  margin: 0 0 0.35rem;
}}
.ow-page-title {{
  margin: 0;
  font-size: clamp(1.45rem, 2.2vw, 1.85rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ow-text);
  line-height: 1.25;
}}
.ow-page-desc {{
  margin: 0.45rem 0 0;
  max-width: 62ch;
  color: var(--ow-text-secondary);
  font-size: 0.98rem;
}}
.ow-page-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}}

/* Cards & surfaces */
.ow-card {{
  background: var(--ow-card);
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius);
  box-shadow: var(--ow-shadow-sm);
  padding: 1rem 1.1rem;
  margin-bottom: 0.85rem;
}}
.ow-card-title {{
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--ow-text);
}}
.ow-card-sub {{
  margin: 0;
  color: var(--ow-text-muted);
  font-size: 0.85rem;
}}

/* KPI strip */
.ow-kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.75rem;
  margin: 0 0 1.25rem;
}}
.ow-kpi {{
  background: var(--ow-card);
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius);
  padding: 0.9rem 1rem;
  box-shadow: var(--ow-shadow-sm);
  min-height: 96px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}
.ow-kpi:focus-within {{
  outline: 2px solid var(--ow-focus);
  outline-offset: 2px;
}}
.ow-kpi-label {{
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--ow-text-muted);
  margin: 0;
}}
.ow-kpi-value {{
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ow-text);
  margin: 0.25rem 0;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}}
.ow-kpi-hint {{
  font-size: 0.8rem;
  color: var(--ow-text-secondary);
  margin: 0;
}}
.ow-kpi[data-tone="success"] {{ border-top: 3px solid var(--ow-success); }}
.ow-kpi[data-tone="warning"] {{ border-top: 3px solid var(--ow-warning); }}
.ow-kpi[data-tone="danger"]  {{ border-top: 3px solid var(--ow-danger); }}
.ow-kpi[data-tone="info"]    {{ border-top: 3px solid var(--ow-info); }}
.ow-kpi[data-tone="primary"] {{ border-top: 3px solid var(--ow-primary); }}

/* Status chips */
.ow-chip {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.3;
  border: 1px solid transparent;
  white-space: nowrap;
}}
.ow-chip::before {{
  content: "";
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}}
.ow-chip-neutral {{ background: var(--ow-muted); color: var(--ow-text-secondary); border-color: var(--ow-border); }}
.ow-chip-success {{ background: var(--ow-success-bg); color: var(--ow-success); }}
.ow-chip-warning {{ background: var(--ow-warning-bg); color: var(--ow-warning); }}
.ow-chip-danger  {{ background: var(--ow-danger-bg); color: var(--ow-danger); }}
.ow-chip-info    {{ background: var(--ow-info-bg); color: var(--ow-info); }}
.ow-chip-primary {{ background: var(--ow-primary-soft); color: var(--ow-primary); }}

/* Callouts / empty / alert banners */
.ow-banner {{
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.85rem 1rem;
  border-radius: var(--ow-radius-sm);
  border: 1px solid var(--ow-border);
  margin: 0 0 1rem;
  background: var(--ow-card);
}}
.ow-banner-icon {{
  font-size: 1.1rem;
  line-height: 1.4;
  flex-shrink: 0;
}}
.ow-banner-body {{ flex: 1; min-width: 0; }}
.ow-banner-title {{
  margin: 0 0 0.15rem;
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--ow-text);
}}
.ow-banner-text {{
  margin: 0;
  color: var(--ow-text-secondary);
  font-size: 0.9rem;
}}
.ow-banner-info    {{ background: var(--ow-info-bg); border-color: #BFDBFE; }}
.ow-banner-success {{ background: var(--ow-success-bg); border-color: #A7F3D0; }}
.ow-banner-warning {{ background: var(--ow-warning-bg); border-color: #FDE68A; }}
.ow-banner-danger  {{ background: var(--ow-danger-bg); border-color: #FECACA; }}

.ow-empty {{
  text-align: center;
  padding: 2rem 1.25rem;
  border: 1px dashed var(--ow-border-strong);
  border-radius: var(--ow-radius);
  background: var(--ow-muted);
  color: var(--ow-text-secondary);
}}
.ow-empty h3 {{
  margin: 0 0 0.35rem;
  color: var(--ow-text);
  font-size: 1.05rem;
}}
.ow-empty p {{ margin: 0; max-width: 42ch; margin-inline: auto; }}

/* Section label */
.ow-section {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 1.35rem 0 0.65rem;
}}
.ow-section h2 {{
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ow-text);
}}
.ow-section p {{
  margin: 0;
  color: var(--ow-text-muted);
  font-size: 0.85rem;
}}

/* Footer strip */
.ow-footer {{
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--ow-border);
  color: var(--ow-text-muted);
  font-size: 0.82rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  justify-content: space-between;
}}

/* Buttons — larger hit targets, clear focus */
.stButton > button,
.stDownloadButton > button,
[data-testid="baseButton-primary"],
[data-testid="baseButton-secondary"] {{
  border-radius: 8px !important;
  min-height: 42px !important;
  font-weight: 600 !important;
  border: 1px solid var(--ow-border) !important;
  transition: background 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease;
}}
.stButton > button:focus-visible,
.stDownloadButton > button:focus-visible,
a:focus-visible,
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:focus-visible {{
  outline: 3px solid var(--ow-focus) !important;
  outline-offset: 2px !important;
  box-shadow: none !important;
}}
div[data-testid="stButton"] > button[kind="primary"],
.stButton > button[kind="primary"] {{
  background: var(--ow-primary) !important;
  color: #fff !important;
  border-color: var(--ow-primary) !important;
}}
div[data-testid="stButton"] > button[kind="primary"]:hover {{
  background: var(--ow-primary-hover) !important;
}}

/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div, .stTextArea textarea, .stDateInput input {{
  border-radius: 8px !important;
  min-height: 42px !important;
  border-color: var(--ow-border-strong) !important;
  background: var(--ow-card) !important;
  color: var(--ow-text) !important;
}}
.stTextInput label, .stSelectbox label, .stMultiSelect label,
.stNumberInput label, .stDateInput label, .stRadio label, .stCheckbox label {{
  font-weight: 600 !important;
  color: var(--ow-text) !important;
}}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{
  gap: 0.25rem;
  border-bottom: 1px solid var(--ow-border);
}}
.stTabs [data-baseweb="tab"] {{
  border-radius: 8px 8px 0 0 !important;
  padding: 0.55rem 0.9rem !important;
  font-weight: 600 !important;
  color: var(--ow-text-secondary) !important;
}}
.stTabs [aria-selected="true"] {{
  color: var(--ow-primary) !important;
  background: var(--ow-primary-soft) !important;
}}

/* Metrics polish */
[data-testid="stMetric"] {{
  background: var(--ow-card);
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius);
  padding: 0.75rem 0.9rem;
  box-shadow: var(--ow-shadow-sm);
}}
[data-testid="stMetricLabel"] {{
  color: var(--ow-text-muted) !important;
  font-weight: 600 !important;
}}
[data-testid="stMetricValue"] {{
  color: var(--ow-text) !important;
  font-variant-numeric: tabular-nums;
}}

/* Dataframes */
[data-testid="stDataFrame"] {{
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius);
  overflow: hidden;
}}

/* Expanders */
[data-testid="stExpander"] {{
  border: 1px solid var(--ow-border) !important;
  border-radius: var(--ow-radius) !important;
  background: var(--ow-card) !important;
}}

/* Dividers */
hr {{
  border: none;
  border-top: 1px solid var(--ow-border);
  margin: 1.25rem 0;
}}

/* Links */
a {{ color: var(--ow-primary); }}
.ow-ul a, .ow-ul .stMarkdown a {{
  text-decoration: underline !important;
  text-underline-offset: 2px;
}}

/* Screen-reader only */
.ow-sr-only {{
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0,0,0,0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}}

/* High contrast boosts */
.ow-hc .ow-kpi,
.ow-hc .ow-card,
.ow-hc [data-testid="stMetric"],
.ow-hc [data-testid="stDataFrame"],
.ow-hc [data-testid="stExpander"] {{
  border-width: 2px !important;
  border-color: #0F172A !important;
}}
.ow-hc .ow-chip {{ border-width: 2px; }}
.ow-hc a {{ text-decoration: underline !important; }}

/* Large text density */
.ow-lg .ow-kpi-value {{ font-size: 1.85rem; }}
.ow-lg .ow-page-title {{ font-size: 2rem !important; }}
.ow-lg .main .block-container {{ max-width: 1180px; }}

/* Reduced motion */
.ow-rm *, .ow-rm *::before, .ow-rm *::after {{
  animation: none !important;
  transition: none !important;
  scroll-behavior: auto !important;
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }}
}}

/* Dark mode surfaces already handled via tokens; tighten Streamlit chrome */
.ow-dark [data-testid="stHeader"] {{
  background: rgba(11, 18, 32, 0.85) !important;
}}
.ow-dark .stTabs [aria-selected="true"] {{
  background: #0C4A6E !important;
  color: #E0F2FE !important;
}}

/* Hide Streamlit chrome clutter without removing keyboard access */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{
  background: transparent;
}}

/* Toolbar / a11y panel */
.ow-a11y-panel {{
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  margin: 0.5rem 0 0.75rem;
}}
.ow-a11y-panel h3 {{
  margin: 0 0 0.35rem !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #9FB0C3 !important;
  font-weight: 600 !important;
}}

/* Persona pill */
.ow-persona {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: rgba(56,189,248,0.12);
  border: 1px solid rgba(56,189,248,0.28);
  color: #E0F2FE !important;
  border-radius: 999px;
  padding: 0.25rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 600;
}}

/* Quick-link tiles on Home */
.ow-tile-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  margin: 0.5rem 0 1.25rem;
}}
.ow-tile {{
  display: block;
  background: var(--ow-card);
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius);
  padding: 1rem;
  text-decoration: none !important;
  color: var(--ow-text) !important;
  box-shadow: var(--ow-shadow-sm);
  min-height: 110px;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}}
.ow-tile:hover {{
  border-color: var(--ow-primary);
  box-shadow: var(--ow-shadow);
}}
.ow-tile:focus-visible {{
  outline: 3px solid var(--ow-focus);
  outline-offset: 2px;
}}
.ow-tile-icon {{
  font-size: 1.25rem;
  margin-bottom: 0.35rem;
}}
.ow-tile strong {{
  display: block;
  font-size: 0.98rem;
  margin-bottom: 0.2rem;
}}
.ow-tile span {{
  color: var(--ow-text-secondary);
  font-size: 0.85rem;
  line-height: 1.4;
}}

/* Status bar */
.ow-statusbar {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.85rem;
  align-items: center;
  padding: 0.55rem 0.85rem;
  background: var(--ow-card);
  border: 1px solid var(--ow-border);
  border-radius: var(--ow-radius-sm);
  margin-bottom: 1rem;
  font-size: 0.85rem;
  color: var(--ow-text-secondary);
}}

/* Apply body class flags via wrapper attribute hack */
div[data-testid="stAppViewContainer"] {{
  /* marker classes applied on descendants via sibling technique */
}}
</style>
<script>
(function () {{
  const flags = {str(body_classes).encode('unicode_escape').decode() if False else ""};
  const classes = "{cls_attr}".trim().split(/\\s+/).filter(Boolean);
  const roots = [
    document.documentElement,
    document.body,
    document.querySelector('[data-testid="stAppViewContainer"]'),
    document.querySelector('.stApp')
  ].filter(Boolean);
  roots.forEach(function (el) {{
    classes.forEach(function (c) {{ el.classList.add(c); }});
  }});
}})();
</script>
<div class="ow-skip-wrap">
  <a class="ow-skip" href="#ow-main-content">Skip to main content</a>
</div>
<div id="ow-main-content" tabindex="-1" class="ow-sr-only">Main content</div>
        """,
        unsafe_allow_html=True,
    )


def animate_home_nav_item() -> None:
    """
    Professional, subtle motion for the sidebar **Home** nav item.
    Injected only from Home.py so other pages stay still.
    Honors prefers-reduced-motion and the in-app Reduced motion a11y flag.
    """
    st.markdown(
        """
<style>
/* —— Home nav item (Home page only) —— */
@keyframes ow-home-glow {
  0%, 100% {
    box-shadow:
      inset 3px 0 0 #38BDF8,
      0 0 0 0 rgba(56, 189, 248, 0.0);
    background: rgba(56, 189, 248, 0.16) !important;
  }
  50% {
    box-shadow:
      inset 3px 0 0 #7DD3FC,
      0 0 14px 0 rgba(56, 189, 248, 0.22);
    background: rgba(56, 189, 248, 0.24) !important;
  }
}
@keyframes ow-home-icon-breathe {
  0%, 100% { transform: translateY(0) scale(1); filter: drop-shadow(0 0 0 rgba(125, 211, 252, 0)); }
  50%      { transform: translateY(-1px) scale(1.06); filter: drop-shadow(0 0 4px rgba(125, 211, 252, 0.55)); }
}
@keyframes ow-home-sheen {
  0%   { transform: translateX(-120%) skewX(-18deg); opacity: 0; }
  35%  { opacity: 0.35; }
  100% { transform: translateX(160%) skewX(-18deg); opacity: 0; }
}
@keyframes ow-home-enter {
  from { opacity: 0.55; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}

[data-testid="stSidebarNav"] a.ow-nav-home {
  position: relative !important;
  overflow: hidden !important;
  isolation: isolate;
  animation:
    ow-home-enter 0.45s cubic-bezier(0.22, 1, 0.36, 1) both,
    ow-home-glow 3.6s ease-in-out 0.45s infinite;
  border: 1px solid rgba(56, 189, 248, 0.22) !important;
  background: rgba(56, 189, 248, 0.16) !important;
  box-shadow: inset 3px 0 0 #38BDF8;
  font-weight: 600 !important;
  letter-spacing: 0.01em;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease !important;
}
[data-testid="stSidebarNav"] a.ow-nav-home::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(
    105deg,
    transparent 40%,
    rgba(255, 255, 255, 0.14) 50%,
    transparent 60%
  );
  animation: ow-home-sheen 4.8s ease-in-out 1.2s infinite;
  pointer-events: none;
  z-index: 0;
}
[data-testid="stSidebarNav"] a.ow-nav-home > * {
  position: relative;
  z-index: 1;
}
/* Material / SVG icon inside the Home link */
[data-testid="stSidebarNav"] a.ow-nav-home svg,
[data-testid="stSidebarNav"] a.ow-nav-home img,
[data-testid="stSidebarNav"] a.ow-nav-home span[data-testid="stIconMaterial"],
[data-testid="stSidebarNav"] a.ow-nav-home [data-testid="stIconMaterial"] {
  animation: ow-home-icon-breathe 3.2s ease-in-out infinite;
  transform-origin: center center;
  display: inline-flex !important;
}
[data-testid="stSidebarNav"] a.ow-nav-home:hover {
  transform: translateX(2px);
  border-color: rgba(125, 211, 252, 0.45) !important;
  background: rgba(56, 189, 248, 0.28) !important;
  box-shadow:
    inset 3px 0 0 #7DD3FC,
    0 4px 16px rgba(14, 165, 233, 0.18) !important;
}
[data-testid="stSidebarNav"] a.ow-nav-home:focus-visible {
  outline: 2px solid #7DD3FC !important;
  outline-offset: 2px !important;
}

/* Reduced motion: keep highlight, drop motion */
.ow-rm [data-testid="stSidebarNav"] a.ow-nav-home,
.ow-rm [data-testid="stSidebarNav"] a.ow-nav-home::before,
.ow-rm [data-testid="stSidebarNav"] a.ow-nav-home svg,
.ow-rm [data-testid="stSidebarNav"] a.ow-nav-home img,
.ow-rm [data-testid="stSidebarNav"] a.ow-nav-home [data-testid="stIconMaterial"] {
  animation: none !important;
  transform: none !important;
  filter: none !important;
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stSidebarNav"] a.ow-nav-home,
  [data-testid="stSidebarNav"] a.ow-nav-home::before,
  [data-testid="stSidebarNav"] a.ow-nav-home svg,
  [data-testid="stSidebarNav"] a.ow-nav-home img,
  [data-testid="stSidebarNav"] a.ow-nav-home [data-testid="stIconMaterial"] {
    animation: none !important;
    transform: none !important;
    filter: none !important;
    transition: none !important;
  }
}
</style>
<script>
(function () {
  const HOME_RE = /^\\s*Home\\s*$/i;
  function mark() {
    const roots = [
      document.querySelector('[data-testid="stSidebar"]'),
      document,
    ].filter(Boolean);
    const seen = new Set();
    roots.forEach(function (root) {
      root.querySelectorAll('[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavLink"]').forEach(function (a) {
        if (seen.has(a)) return;
        seen.add(a);
        const label = (a.textContent || "").replace(/\\s+/g, " ").trim();
        // Exact "Home" only — never other pages that contain the word
        if (HOME_RE.test(label)) {
          a.classList.add("ow-nav-home");
          a.setAttribute("data-ow-home-nav", "1");
        } else {
          a.classList.remove("ow-nav-home");
          a.removeAttribute("data-ow-home-nav");
        }
      });
    });
  }
  mark();
  // Streamlit re-renders the sidebar; keep the class applied
  let tries = 0;
  const tick = setInterval(function () {
    mark();
    tries += 1;
    if (tries > 40) clearInterval(tick);
  }, 250);
  try {
    const side = document.querySelector('[data-testid="stSidebar"]');
    if (side && window.MutationObserver) {
      const mo = new MutationObserver(function () { mark(); });
      mo.observe(side, { childList: true, subtree: true });
    }
  } catch (e) { /* ignore */ }
})();
</script>
        """,
        unsafe_allow_html=True,
    )


def plotly_layout(**overrides):
    """Return a copy of the shared Plotly layout with optional overrides."""
    layout = {**PLOTLY_LAYOUT}
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(layout.get(key), dict):
            layout[key] = {**layout[key], **value}
        else:
            layout[key] = value
    if st.session_state.get("a11y_dark_mode"):
        layout = {
            **layout,
            "font": {**layout.get("font", {}), "color": "#E2E8F0"},
            "xaxis": {
                **layout.get("xaxis", {}),
                "gridcolor": "#334155",
                "linecolor": "#475569",
                "tickfont": {"color": "#CBD5E1"},
            },
            "yaxis": {
                **layout.get("yaxis", {}),
                "gridcolor": "#334155",
                "linecolor": "#475569",
                "tickfont": {"color": "#CBD5E1"},
            },
            "legend": {
                **layout.get("legend", {}),
                "bgcolor": "rgba(17,24,39,0.9)",
                "bordercolor": "#334155",
                "font": {"color": "#E2E8F0"},
            },
        }
    if st.session_state.get("a11y_large_text"):
        base_font = dict(layout.get("font") or {})
        base_font["size"] = max(int(base_font.get("size") or 13) + 2, 15)
        layout["font"] = base_font
    return layout


# Public exports (explicit so `from ow_theme import apply_theme` never fails
# due to partial loads / stale renames). `apply` is a legacy alias.
apply = apply_theme

__all__ = [
    "COLORS",
    "NAVY",
    "NAVY_MID",
    "TEAL",
    "TEAL_DARK",
    "SKY",
    "CORAL",
    "AMBER",
    "GREEN",
    "TEXT",
    "TEXT_MUTED",
    "BG",
    "CARD",
    "BORDER",
    "BORDER_STRONG",
    "PLOTLY_DEFAULTS",
    "init_a11y_defaults",
    "apply_theme",
    "apply",
    "plotly_layout",
]

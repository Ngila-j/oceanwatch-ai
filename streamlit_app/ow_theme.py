"""OceanWatch dark sidebar theme — match product canvas."""
import streamlit as st


def apply():
    st.markdown(
        """
<style>
  /* Sidebar shell — navy like the canvas */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1f33 0%, #0d2137 55%, #0a1929 100%);
  }
  [data-testid="stSidebar"] > div:first-child {
    background: transparent;
  }
  /* Nav labels */
  [data-testid="stSidebar"] * {
    color: #e8eef5 !important;
  }
  [data-testid="stSidebar"] span {
    font-size: 0.92rem;
  }
  /* Section headers in st.navigation */
  [data-testid="stSidebarNav"] {
    padding-top: 0.5rem;
  }
  [data-testid="stSidebarNav"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #8b9cb3 !important;
    font-size: 0.72rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  /* Active / hover */
  [data-testid="stSidebarNav"] a:hover {
    background-color: rgba(31, 111, 235, 0.25) !important;
    border-radius: 6px;
  }
  [data-testid="stSidebarNav"] a[aria-current="page"] {
    background-color: rgba(31, 111, 235, 0.35) !important;
    border-radius: 6px;
    border-left: 3px solid #4c8bf5;
  }
  /* Main canvas */
  .block-container {
    padding-top: 1.2rem;
  }
  /* Hide default footer clutter a bit */
  footer { visibility: hidden; }
</style>
        """,
        unsafe_allow_html=True,
    )
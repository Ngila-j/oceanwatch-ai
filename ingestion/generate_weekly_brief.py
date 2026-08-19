"""
OceanWatch Phase 10 — Weekly Ocean Brief (PDF)

Pulls latest Kenya EEZ KPIs and writes reports/weekly_ocean_brief_YYYYMMDD.pdf
Requires: reportlab (install in Airflow image or host).
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def get_output_dir() -> Path:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        p = Path("/opt/airflow/data/reports")
    else:
        p = Path(__file__).resolve().parents[1] / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def q(conn, sql: str):
    try:
        return conn.execute(text(sql)).mappings().first()
    except Exception as e:
        logger.warning("Query skipped: %s", e)
        return None


def main():
    logger.info("=== Weekly Ocean Brief ===")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.error("reportlab not installed. Run: pip install reportlab")
        raise

    engine = create_engine(get_db_uri())
    out_dir = get_output_dir()
    today = date.today()
    out_path = out_dir / f"weekly_ocean_brief_{today.strftime('%Y%m%d')}.pdf"

    with engine.connect() as conn:
        wio = q(
            conn,
            """
            SELECT * FROM fact_wio_intelligence_index
            ORDER BY index_date DESC LIMIT 1
            """,
        )
        port = q(
            conn,
            """
            SELECT * FROM fact_port_metrics
            ORDER BY metric_date DESC LIMIT 1
            """,
        )
        bloom = q(
            conn,
            """
            SELECT * FROM fact_bloom_risk
            ORDER BY risk_date DESC LIMIT 1
            """,
        )
        gfw = q(
            conn,
            """
            SELECT COUNT(*) AS cells, COALESCE(SUM(hours),0) AS hours
            FROM fact_gfw_fishing_effort
            """,
        )
        sst = q(
            conn,
            """
            SELECT AVG(sst_celsius) AS sst
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
              AND date_key >= CURRENT_DATE - INTERVAL '7 days'
            """,
        )

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    def line(text, size=11, gap=16):
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(2 * cm, y, str(text)[:110])
        y -= gap

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "OceanWatch AI — Weekly Ocean Brief")
    y -= 22
    line(f"Region: Kenya EEZ / Mombasa  |  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", 10)
    line("Prototype operational summary — not an official government product.", 9)
    y -= 8

    line("1. WIO Ocean Intelligence Index (WIO-OII)", 12)
    if wio:
        line(f"   Overall: {wio.get('overall_score')} / 100   Confidence: {wio.get('confidence_score')}%")
        line(f"   Method: {wio.get('methodology_version')}   Date: {wio.get('index_date')}")
        line(f"   Drivers: {str(wio.get('drivers') or '')[:90]}")
    else:
        line("   No index row available.")

    y -= 6
    line("2. Port snapshot (Mombasa)", 12)
    if port:
        line(f"   Arrivals: {port.get('arrivals')}  Departures: {port.get('departures')}  Active: {port.get('active_vessels')}")
        line(f"   Congestion: {port.get('congestion_level')} ({port.get('congestion_index')})  Wait(h): {port.get('avg_waiting_hours')}")
    else:
        line("   No port metrics.")

    y -= 6
    line("3. Environment & fisheries", 12)
    if sst and sst.get("sst") is not None:
        line(f"   Mean SST (7d): {float(sst['sst']):.2f} °C")
    if bloom:
        line(f"   Bloom risk: {bloom.get('risk_level')}  prob={bloom.get('bloom_probability')}")
    if gfw:
        line(f"   GFW effort cells: {gfw.get('cells')}  hours: {float(gfw.get('hours') or 0):.1f}")
        line("   Fishing effort powered by Global Fishing Watch (non-commercial attribution).")

    y -= 10
    line("4. Product / access notes", 12)
    line("   Dashboard: Streamlit multi-persona views")
    line("   Partner API: http://localhost:8000/docs  (read-only v0.8.x)")
    line("   Tiers (planned): Public | Research | Agency SaaS | Custom alerts")

    y -= 10
    line("Disclaimer: Scores are engineering prototypes with documented methodology.", 8)
    line("Contact: OceanWatch AI project — Kenya-first Western Indian Ocean focus.", 8)

    c.showPage()
    c.save()
    logger.info("Wrote %s", out_path)
    logger.info("=== Weekly Ocean Brief completed ===")
    print(str(out_path))


if __name__ == "__main__":
    main()
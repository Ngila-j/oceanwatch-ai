"""
OceanWatch alert delivery (S3 Reach)
Outbox always; email when SMTP_* + ALERT_EMAIL_TO (or subscription emails) work.
"""

import logging
import os
import smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SEVERITIES = ("ELEVATED", "HIGH", "CRITICAL")


def load_env():
    for p in (
        Path("/opt/airflow/ingestion/.env"),
        Path(__file__).resolve().parent / ".env",
    ):
        if p.exists():
            load_dotenv(p, override=True)
            logger.info("Loaded env from %s", p)
            return
    logger.warning("No .env found")


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def outbox_dir() -> Path:
    for p in (
        Path("/opt/airflow/data/alerts_outbox"),
        Path(__file__).resolve().parents[1] / "data" / "alerts_outbox",
        Path.cwd() / "data" / "alerts_outbox",
    ):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    p = Path("/tmp/alerts_outbox")
    p.mkdir(parents=True, exist_ok=True)
    return p


def connect():
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
    return con


def load_alerts(con) -> pd.DataFrame:
    sev = ", ".join(f"'{s}'" for s in SEVERITIES)
    try:
        return con.execute(
            f"""
            SELECT severity, category, title, description, why_it_matters,
                   data_source, vessel_name, location_label, risk_score,
                   created_at, status
            FROM pg.public.fact_alerts
            WHERE status = 'OPEN'
              AND UPPER(severity) IN ({sev})
            ORDER BY created_at DESC
            LIMIT 50
            """
        ).fetchdf()
    except Exception as e:
        logger.error("Could not load alerts: %s", e)
        return pd.DataFrame()


def load_subscriptions(con) -> pd.DataFrame:
    try:
        return con.execute(
            "SELECT * FROM pg.public.alert_subscriptions"
        ).fetchdf()
    except Exception as e:
        logger.info("Subscriptions unavailable: %s", e)
        return pd.DataFrame()


def format_digest(alerts: pd.DataFrame) -> str:
    lines = [
        f"OceanWatch Alert Digest — {date.today().isoformat()}",
        "Region: Kenya EEZ / Western Indian Ocean",
        "Decision-support only. Not an official authority notice.",
        "",
        f"Elevated+ open alerts: {len(alerts)}",
        "",
    ]
    if alerts.empty:
        lines.append("No ELEVATED/HIGH/CRITICAL open alerts.")
    else:
        for _, a in alerts.iterrows():
            lines.append(f"- [{a.get('severity')}] {a.get('title')} ({a.get('category')})")
            if a.get("why_it_matters"):
                lines.append(f"  Why it matters: {a.get('why_it_matters')}")
            if a.get("description"):
                lines.append(f"  Detail: {a.get('description')}")
            lines.append("")
    lines.append(
        "Anomalies and vessel scores are not legal determinations. "
        "GFW-related content: Global Fishing Watch terms/attribution apply."
    )
    return "\n".join(lines)


def write_outbox(text: str) -> Path:
    path = outbox_dir() / f"alert_digest_{date.today().isoformat()}.txt"
    path.write_text(text, encoding="utf-8")
    logger.info("Outbox written: %s", path)
    return path


def recipient_list(subs: pd.DataFrame) -> list:
    emails = []
    if subs is not None and not subs.empty:
        for col in ("email", "subscriber_email", "contact_email", "target", "address"):
            if col in subs.columns:
                for x in subs[col].dropna():
                    s = str(x).strip()
                    if s and "@" in s:
                        emails.append(s)
    # Always allow env fallback
    default = (os.getenv("ALERT_EMAIL_TO") or "").strip()
    for e in default.split(","):
        e = e.strip()
        if e and "@" in e:
            emails.append(e)
    return sorted(set(emails))


def send_email(text: str, recipients: list) -> None:
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or "587")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    sender = (os.getenv("SMTP_FROM") or user or "oceanwatch@localhost").strip()

    logger.info(
        "Email check: host=%s user=%s recipients=%s pass=%s",
        bool(host),
        bool(user),
        len(recipients),
        bool(password),
    )

    if not host or not recipients:
        logger.info("SMTP not configured or no recipients — skip email")
        return

    msg = MIMEText(text)
    msg["Subject"] = f"OceanWatch Alert Digest {date.today().isoformat()}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    try:
        with smtplib.SMTP(host, port, timeout=45) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        logger.info("Email sent to %s", recipients)
    except Exception as e:
        logger.error("Email send failed: %s", e)


def main():
    load_env()
    logger.info("=== Alert delivery (S3) ===")
    con = connect()
    alerts = load_alerts(con)
    subs = load_subscriptions(con)
    text = format_digest(alerts)
    write_outbox(text)
    recipients = recipient_list(subs)
    send_email(text, recipients)
    logger.info("=== Alert delivery completed ===")


if __name__ == "__main__":
    main()
"""Phase 8 product tables: roles + alert subscriptions (SQLAlchemy / Supabase-safe)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_db_uri() -> str:
    _load_env()
    try:
        from db_utils import get_db_uri as _g

        uri = _g()
    except Exception:  # noqa: BLE001
        uri = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or ""
    if not uri:
        raise RuntimeError("OCEANWATCH_DB_URI / DATABASE_URL not set")
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def _engine():
    uri = get_db_uri()
    args = {"connect_timeout": 20, "options": "-c statement_timeout=60000"}
    if "supabase" in uri.lower() or "pooler" in uri.lower():
        args["sslmode"] = "require"
    return create_engine(uri, pool_pre_ping=True, connect_args=args, pool_size=1, max_overflow=0)


DDL_USER_ROLES = """
CREATE TABLE IF NOT EXISTS user_roles (
    user_id VARCHAR PRIMARY KEY,
    role VARCHAR NOT NULL,
    organization VARCHAR,
    access_level VARCHAR NOT NULL,
    email VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_ALERT_SUBS = """
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR,
    role VARCHAR,
    organization VARCHAR,
    alert_type VARCHAR NOT NULL,
    region VARCHAR DEFAULT 'Kenya EEZ',
    severity_threshold VARCHAR DEFAULT 'MEDIUM',
    channel VARCHAR DEFAULT 'email',
    destination VARCHAR,
    email_enabled BOOLEAN DEFAULT TRUE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

DEMO_ROLES = [
    ("demo_port", "port_operator", "Demo Org", "operational", "port@demo.local"),
    ("demo_fish", "fisheries_user", "Demo Org", "operational", "fish@demo.local"),
    ("demo_env", "environment_user", "Demo Org", "analyst", "env@demo.local"),
    ("demo_research", "researcher", "Demo Org", "read", "research@demo.local"),
]

DEMO_SUBS = [
    ("demo_port", "port_operator", "Demo Org", "PORT_RISK", "Kenya EEZ", "MEDIUM", "email", "port@demo.local", True),
    ("demo_fish", "fisheries_user", "Demo Org", "FISHING_ACTIVITY", "Kenya EEZ", "HIGH", "email", "fish@demo.local", True),
    ("demo_env", "environment_user", "Demo Org", "BLOOM_RISK", "Kenya EEZ", "MEDIUM", "email", "env@demo.local", True),
]


def main() -> None:
    logger.info("=== Phase 8 product schema ===")
    eng = _engine()

    with eng.begin() as conn:
        conn.execute(text(DDL_USER_ROLES))
        conn.execute(text(DDL_ALERT_SUBS))

        # Ensure columns on older partial schemas
        for ddl in (
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS role VARCHAR",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS organization VARCHAR",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS region VARCHAR DEFAULT 'Kenya EEZ'",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS severity_threshold VARCHAR DEFAULT 'MEDIUM'",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS channel VARCHAR DEFAULT 'email'",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS destination VARCHAR",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS email_enabled BOOLEAN DEFAULT TRUE",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE",
            "ALTER TABLE alert_subscriptions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        ):
            try:
                conn.execute(text(ddl))
            except Exception:  # noqa: BLE001
                pass

        # Seed roles (upsert)
        for user_id, role, org, access, email in DEMO_ROLES:
            conn.execute(
                text(
                    """
                    INSERT INTO user_roles (user_id, role, organization, access_level, email)
                    VALUES (:user_id, :role, :org, :access, :email)
                    ON CONFLICT (user_id) DO UPDATE SET
                        role = EXCLUDED.role,
                        organization = EXCLUDED.organization,
                        access_level = EXCLUDED.access_level,
                        email = EXCLUDED.email
                    """
                ),
                {
                    "user_id": user_id,
                    "role": role,
                    "org": org,
                    "access": access,
                    "email": email,
                },
            )

        # Seed demo subscriptions only if table empty
        n = conn.execute(text("SELECT COUNT(*) FROM alert_subscriptions")).scalar() or 0
        if int(n) == 0:
            for user_id, role, org, alert_type, region, sev, channel, dest, email_on in DEMO_SUBS:
                conn.execute(
                    text(
                        """
                        INSERT INTO alert_subscriptions (
                            user_id, role, organization, alert_type, region,
                            severity_threshold, channel, destination, email_enabled, active
                        ) VALUES (
                            :user_id, :role, :org, :alert_type, :region,
                            :sev, :channel, :dest, :email_on, TRUE
                        )
                        """
                    ),
                    {
                        "user_id": user_id,
                        "role": role,
                        "org": org,
                        "alert_type": alert_type,
                        "region": region,
                        "sev": sev,
                        "channel": channel,
                        "dest": dest,
                        "email_on": email_on,
                    },
                )
            logger.info("Seeded %s demo alert subscriptions", len(DEMO_SUBS))
        else:
            logger.info("alert_subscriptions already has %s rows — skip seed", n)

        roles_n = conn.execute(text("SELECT COUNT(*) FROM user_roles")).scalar()
        subs_n = conn.execute(text("SELECT COUNT(*) FROM alert_subscriptions")).scalar()
        logger.info("user_roles=%s alert_subscriptions=%s", roles_n, subs_n)

    logger.info("=== Phase 8 ready ===")
    eng.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        logger.exception("init_phase8_product failed: %s", e)
        sys.exit(1)

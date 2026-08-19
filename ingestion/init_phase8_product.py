"""Phase 8 product tables: roles + alert subscriptions."""
import os
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Phase 8 product schema ===")
    engine = create_engine(get_db_uri())

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id VARCHAR PRIMARY KEY,
                role VARCHAR NOT NULL,
                organization VARCHAR,
                access_level VARCHAR NOT NULL,
                email VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_subscriptions (
                subscription_id BIGSERIAL PRIMARY KEY,
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
            );
        """))

        conn.execute(text("DELETE FROM user_roles;"))
        conn.execute(text("""
            INSERT INTO user_roles (user_id, role, organization, access_level, email) VALUES
            ('demo_admin', 'admin', 'OceanWatch', 'SENSITIVE', 'admin@oceanwatch.local'),
            ('demo_port', 'port_operator', 'Kenya Ports Authority', 'RESTRICTED', 'port@oceanwatch.local'),
            ('demo_fish', 'fisheries_user', 'BMU Demo', 'RESTRICTED', 'fisheries@oceanwatch.local'),
            ('demo_mda', 'maritime_user', 'Coast Guard Demo', 'SENSITIVE', 'mda@oceanwatch.local'),
            ('demo_nema', 'environment_user', 'NEMA Demo', 'RESTRICTED', 'nema@oceanwatch.local'),
            ('demo_research', 'researcher', 'University Demo', 'PUBLIC', 'research@oceanwatch.local'),
            ('demo_public', 'public', 'Public', 'PUBLIC', NULL);
        """))

    logger.info("=== Phase 8 schema ready ===")


if __name__ == "__main__":
    main()
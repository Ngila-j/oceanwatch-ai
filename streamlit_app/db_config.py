"""
Database URI resolution for local + Streamlit Community Cloud.

Order:
  1. st.secrets["OCEANWATCH_DB_URI"] or st.secrets["DATABASE_URL"]
  2. st.secrets["db"]["uri"] (or host/user/password/database/port)
  3. env OCEANWATCH_DB_URI / DATABASE_URL
  4. local docker-compose default (dev only)

Always returns a postgresql+psycopg2:// URI so SQLAlchemy 2.1+ uses
psycopg2-binary (installed) instead of the default psycopg (v3) driver.
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import quote_plus

_LOCAL_DEFAULT = "postgresql+psycopg2://postgres:password@localhost:5433/oceanwatch_db"


def _as_psycopg2(uri: str) -> str:
    """Force psycopg2 dialect (SQLAlchemy 2.1 defaults bare postgresql:// to psycopg v3)."""
    u = (uri or "").strip()
    if not u:
        return u
    if u.startswith("postgresql+psycopg2://"):
        return u
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    return u


def _from_streamlit_secrets() -> str | None:
    try:
        import streamlit as st

        secrets = st.secrets  # may raise if no secrets file
    except Exception:
        return None

    try:
        if "OCEANWATCH_DB_URI" in secrets:
            return str(secrets["OCEANWATCH_DB_URI"]).strip()
        if "DATABASE_URL" in secrets:
            return str(secrets["DATABASE_URL"]).strip()

        db = secrets.get("db", None)
        if db is None:
            return None
        # TOML [db] uri = "..."
        if "uri" in db and db["uri"]:
            return str(db["uri"]).strip()
        # TOML [db] host/user/password/database/port
        host = db.get("host")
        user = db.get("user") or db.get("username")
        password = db.get("password")
        database = db.get("database") or db.get("dbname") or "oceanwatch_db"
        port = db.get("port", 5432)
        if host and user and password is not None:
            user_q = quote_plus(str(user))
            pass_q = quote_plus(str(password))
            return f"postgresql://{user_q}:{pass_q}@{host}:{port}/{database}"
    except Exception:
        return None
    return None


@lru_cache(maxsize=1)
def get_db_uri() -> str:
    """Return the active Postgres URI (cached per process), dialect-pinned to psycopg2."""
    secret_uri = _from_streamlit_secrets()
    if secret_uri:
        return _as_psycopg2(secret_uri)

    env_uri = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")
    if env_uri:
        return _as_psycopg2(env_uri.strip())

    return _LOCAL_DEFAULT


# Back-compat alias used by older pages
def get_database_url() -> str:
    return get_db_uri()

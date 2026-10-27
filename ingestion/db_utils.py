"""
Shared DuckDB→Postgres helpers for OceanWatch ingestion jobs.

Centralizes URI resolution, attach, safe writes, and query helpers so
phase scripts stop duplicating hardcoded credentials and DELETE/INSERT paths.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_HOST_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
_DEFAULT_DOCKER_URI = "postgresql://postgres:password@postgres:5432/oceanwatch_db"


def _load_ingestion_dotenv() -> None:
    """Load ingestion/.env into os.environ (setdefault — does not override)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def get_db_uri() -> str:
    """
    Prefer OCEANWATCH_DB_URI / DATABASE_URL (Supabase, managed Postgres, local).
    Loads ingestion/.env when present. Fall back to Docker / localhost:5433.
    """
    _load_ingestion_dotenv()
    for key in ("OCEANWATCH_DB_URI", "DATABASE_URL"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            # DuckDB postgres scanner wants postgresql:// not SQLAlchemy dialect URLs
            return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
                "postgres://", "postgresql://"
            )
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return _DEFAULT_DOCKER_URI
    return _DEFAULT_HOST_URI


def attach_postgres(con: Optional[duckdb.DuckDBPyConnection] = None, alias: str = "pg"):
    """Return a DuckDB connection with Postgres attached as `alias`."""
    uri = get_db_uri()
    if con is None:
        con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    # DETACH if re-attaching
    try:
        con.execute(f"DETACH {alias}")
    except Exception:  # noqa: BLE001 — no cover - best-effort cleanup
        pass
    con.execute(f"ATTACH '{uri}' AS {alias} (TYPE POSTGRES)")
    return con


def table_columns(con, table: str, schema: str = "public", catalog: str = "pg") -> list[str]:
    try:
        rows = con.execute(
            f"""
            SELECT column_name
            FROM {catalog}.information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table],
        ).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return []


def qdf(con, sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:  # noqa: BLE001
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def write_df(
    con,
    table: str,
    df: pd.DataFrame,
    *,
    replace: bool = False,
    schema: str = "public",
    catalog: str = "pg",
) -> int:
    """Insert DataFrame into Postgres table (optionally DELETE all first)."""
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return 0
    cols = table_columns(con, table, schema=schema, catalog=catalog)
    use = [c for c in df.columns if c in cols]
    if not use:
        logger.warning("No matching columns for %s (df=%s table=%s)", table, list(df.columns), cols)
        return 0
    fq = f"{catalog}.{schema}.{table}"
    if replace:
        con.execute(f"DELETE FROM {fq}")
    con.register("_ow_write_df", df[use])
    col_list = ", ".join(use)
    con.execute(f"INSERT INTO {fq} ({col_list}) SELECT {col_list} FROM _ow_write_df")
    n = len(df)
    logger.info("%s: %s rows", table, n)
    return n


def replace_rows(con, table: str, rows: Iterable[dict], **kwargs) -> int:
    return write_df(con, table, pd.DataFrame(list(rows)), replace=True, **kwargs)

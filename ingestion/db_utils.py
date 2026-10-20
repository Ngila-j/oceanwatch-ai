"""
Shared DuckDB→Postgres helpers for OceanWatch ingestion jobs.

Centralizes URI resolution, attach, safe writes, and query helpers so
phase scripts stop duplicating hardcoded credentials and DELETE/INSERT logic.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional, Sequence

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_HOST_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
_DEFAULT_DOCKER_URI = "postgresql://postgres:password@postgres:5432/oceanwatch_db"


def get_db_uri() -> str:
    """Resolve Postgres URI from env, with host vs container defaults."""
    explicit = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return os.getenv("OCEANWATCH_DB_URI_DOCKER", _DEFAULT_DOCKER_URI)
    return _DEFAULT_HOST_URI


@contextmanager
def pg_connection() -> Iterator["duckdb.DuckDBPyConnection"]:
    """Attach Postgres as `pg` and always close the DuckDB handle."""
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
        yield con
    finally:
        try:
            con.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def table_columns(con, table: str, schema: str = "public") -> list[str]:
    try:
        rows = con.execute(
            """
            SELECT column_name
            FROM pg.information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table],
        ).fetchall()
        return [r[0] for r in rows]
    except Exception as exc:
        logger.warning("Could not list columns for %s.%s: %s", schema, table, exc)
        return []


def qdf(con, sql: str, params: Optional[Sequence] = None) -> pd.DataFrame:
    try:
        if params is None:
            return con.execute(sql).fetchdf()
        return con.execute(sql, list(params)).fetchdf()
    except Exception as exc:
        logger.warning("Query failed: %s | sql=%s", exc, sql[:180])
        return pd.DataFrame()


def write_frame(
    con,
    table: str,
    df: pd.DataFrame,
    *,
    replace: bool = False,
    schema: str = "public",
) -> int:
    """
    Insert a DataFrame into pg.<schema>.<table>.

    replace=True deletes all rows first (use only for small dim/registry tables).
    Returns number of rows written.
    """
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return 0

    available = set(table_columns(con, table, schema=schema))
    if not available:
        logger.warning("No columns for %s — skip write", table)
        return 0

    use = [c for c in df.columns if c in available]
    if not use:
        logger.warning("No overlapping columns for %s", table)
        return 0

    fq = f"pg.{schema}.{table}"
    if replace:
        con.execute(f"DELETE FROM {fq}")

    tmp = f"_ow_tmp_{table}"
    con.register(tmp, df[use].copy())
    cols_sql = ", ".join(use)
    con.execute(f"INSERT INTO {fq} ({cols_sql}) SELECT {cols_sql} FROM {tmp}")
    try:
        con.unregister(tmp)
    except Exception:
        pass
    logger.info("%s: %s rows (replace=%s)", table, len(df), replace)
    return len(df)


def upsert_topics(con, rows: Iterable[dict]) -> None:
    """Replace topic registry (small static set)."""
    write_frame(con, "event_bus_topics", pd.DataFrame(list(rows)), replace=True)


def upsert_consumers(con, rows: Iterable[dict]) -> None:
    """Replace consumer registry (small static set)."""
    write_frame(con, "event_bus_consumers", pd.DataFrame(list(rows)), replace=True)

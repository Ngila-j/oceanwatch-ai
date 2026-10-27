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
from urllib.parse import urlparse, urlunparse

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


def prefer_session_pooler(uri: str) -> str:
    """
    Supabase transaction pooler (:6543) is often read-only for DDL/DML from
    external clients; prefer session-mode pooler on :5432 for writes.
    """
    if not uri:
        return uri
    try:
        parsed = urlparse(uri)
        host = (parsed.hostname or "").lower()
        if (
            parsed.port == 6543
            and "pooler.supabase" in host
            and parsed.username
            and parsed.password
        ):
            return urlunparse(
                parsed._replace(
                    netloc=f"{parsed.username}:{parsed.password}@{parsed.hostname}:5432"
                )
            )
    except Exception:  # noqa: BLE001
        pass
    return uri


def get_db_uri() -> str:
    """
    Prefer OCEANWATCH_DB_URI / DATABASE_URL (Supabase, managed Postgres, local).
    Loads ingestion/.env when present. Fall back to Docker / localhost:5433.
    Rewrites Supabase :6543 transaction pooler to :5432 session pooler for DDL.
    """
    _load_ingestion_dotenv()
    for key in ("OCEANWATCH_DB_URI", "DATABASE_URL"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            # DuckDB postgres scanner wants postgresql:// not SQLAlchemy dialect URLs
            uri = raw.replace("postgresql+psycopg2://", "postgresql://").replace(
                "postgres://", "postgresql://"
            )
            return prefer_session_pooler(uri)
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
    """Run SQL and return a DataFrame (DuckDB or psycopg/SQLAlchemy-style con)."""
    try:
        result = con.execute(sql)
        if hasattr(result, "fetchdf"):
            return result.fetchdf()
        cols = [d[0] for d in (result.description or [])]
        rows = result.fetchall() if hasattr(result, "fetchall") else list(result)
        return pd.DataFrame(rows, columns=cols)
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


# ---------------------------------------------------------------------------
# SQLAlchemy / psycopg helpers (Phase 22+ event bus & notifications)
# ---------------------------------------------------------------------------

from contextlib import contextmanager


class _PsycopgProxy:
    """Thin connection proxy: .execute(sql, params) -> cursor (psycopg2-style)."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        if params is None:
            cur.execute(sql)
        else:
            cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def pg_connection():
    """Yield a Postgres connection proxy (psycopg2). Commits on success."""
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover
        raise ImportError("psycopg2 is required for pg_connection()") from exc

    uri = get_db_uri()
    raw = psycopg2.connect(uri)
    proxy = _PsycopgProxy(raw)
    try:
        yield proxy
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _pg_table_columns(con, table: str, schema: str = "public") -> list[str]:
    try:
        cur = con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [r[0] for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def write_frame(
    con,
    table: str,
    df: Optional[pd.DataFrame],
    replace: bool = False,
    schema: str = "public",
) -> int:
    """Insert rows via psycopg proxy. replace=True deletes existing rows first."""
    if df is None or getattr(df, "empty", True):
        logger.info("%s: 0 rows", table)
        return 0

    cols = _pg_table_columns(con, table, schema=schema)
    use = [c for c in df.columns if c in cols] if cols else list(df.columns)
    if not use:
        logger.warning("No columns for %s", table)
        return 0

    fq = f"{schema}.{table}" if schema else table
    if replace:
        con.execute(f"DELETE FROM {fq}")

    placeholders = ", ".join(["%s"] * len(use))
    col_list = ", ".join(use)
    sql = f"INSERT INTO {fq} ({col_list}) VALUES ({placeholders})"

    work = df[use].copy()
    # Normalize timestamps / NaN -> None for psycopg
    for c in work.columns:
        if pd.api.types.is_datetime64_any_dtype(work[c]):
            work[c] = work[c].astype(object).where(work[c].notna(), None)
    records = []
    for row in work.itertuples(index=False, name=None):
        records.append(tuple(None if (v is pd.NA or (isinstance(v, float) and pd.isna(v))) else v for v in row))

    cur = con.execute("SELECT 1")  # ensure cursor factory path
    # use underlying connection for executemany
    raw = getattr(con, "_conn", None)
    if raw is not None:
        with raw.cursor() as c2:
            c2.executemany(sql, records)
    else:
        for rec in records:
            con.execute(sql, rec)

    n = len(records)
    logger.info("%s: %s rows", table, n)
    return n


def upsert_topics(con, topics: Iterable[dict]) -> int:
    """Upsert event_bus_topics on primary key `topic`."""
    n = 0
    for t in topics or []:
        con.execute(
            """
            INSERT INTO event_bus_topics (topic, description, status, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (topic) DO UPDATE SET
                description = EXCLUDED.description,
                status = EXCLUDED.status
            """,
            (
                t.get("topic"),
                t.get("description"),
                t.get("status", "ACTIVE"),
                t.get("created_at"),
            ),
        )
        n += 1
    logger.info("event_bus_topics upserted: %s", n)
    return n


def upsert_consumers(con, consumers: Iterable[dict]) -> int:
    """Upsert event_bus_consumers on primary key `consumer_id`."""
    n = 0
    for c in consumers or []:
        con.execute(
            """
            INSERT INTO event_bus_consumers
                (consumer_id, consumer_name, topics, status, last_seen_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (consumer_id) DO UPDATE SET
                consumer_name = EXCLUDED.consumer_name,
                topics = EXCLUDED.topics,
                status = EXCLUDED.status,
                last_seen_at = EXCLUDED.last_seen_at
            """,
            (
                c.get("consumer_id"),
                c.get("consumer_name"),
                c.get("topics"),
                c.get("status", "ACTIVE"),
                c.get("last_seen_at"),
            ),
        )
        n += 1
    logger.info("event_bus_consumers upserted: %s", n)
    return n

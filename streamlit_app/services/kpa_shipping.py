"""KPA 14-day shipping movement — parse upload + warehouse read."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _resolve_uri() -> str:
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        pass
    app = Path(__file__).resolve().parents[1]
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    try:
        from db_config import get_db_uri

        return get_db_uri()
    except Exception:  # noqa: BLE001
        pass
    ing = Path(__file__).resolve().parents[2] / "ingestion"
    if str(ing) not in sys.path:
        sys.path.insert(0, str(ing))
    from db_utils import get_db_uri as _g  # type: ignore

    return _g()


def _sa_uri(uri: str) -> str:
    u = (uri or "").strip()
    if u.startswith("postgresql+psycopg2://"):
        return u
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    return u


class KPAShippingService:
    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or create_engine(
            _sa_uri(_resolve_uri()),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            connect_args={"connect_timeout": 25},
        )
        self._ing_path = Path(__file__).resolve().parents[2] / "ingestion"
        if str(self._ing_path) not in sys.path:
            sys.path.insert(0, str(self._ing_path))

    def ensure_schema(self) -> None:
        try:
            from init_kpa_and_live_feeds import main as init_main

            init_main()
        except Exception:  # noqa: BLE001
            pass

    def qdf(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

    def table_exists(self, name: str) -> bool:
        df = self.qdf(
            """
            SELECT 1 AS ok FROM information_schema.tables
            WHERE table_schema='public' AND table_name=:n LIMIT 1
            """,
            {"n": name},
        )
        return not df.empty

    def latest_report_date(self) -> Optional[str]:
        df = self.qdf("SELECT MAX(report_date) AS d FROM fact_kpa_shipping_movement")
        if df.empty or df.iloc[0]["d"] is None:
            return None
        return str(df.iloc[0]["d"])[:10]

    def movements(self, report_date: Optional[str] = None, limit: int = 500) -> pd.DataFrame:
        if not self.table_exists("fact_kpa_shipping_movement"):
            return pd.DataFrame()
        if report_date:
            return self.qdf(
                """
                SELECT * FROM fact_kpa_shipping_movement
                WHERE report_date = :d
                ORDER BY eta NULLS LAST, vessel_name
                LIMIT :lim
                """,
                {"d": report_date, "lim": limit},
            )
        return self.qdf(
            """
            SELECT * FROM fact_kpa_shipping_movement
            WHERE report_date = (SELECT MAX(report_date) FROM fact_kpa_shipping_movement)
               OR report_date IS NULL
            ORDER BY report_date DESC NULLS LAST, eta NULLS LAST, vessel_name
            LIMIT :lim
            """,
            {"lim": limit},
        )

    def summary(self) -> dict[str, Any]:
        if not self.table_exists("fact_kpa_shipping_movement"):
            return {"rows": 0, "report_date": None, "vessels": 0}
        df = self.qdf(
            """
            SELECT
              COUNT(*) AS rows,
              COUNT(DISTINCT vessel_name) AS vessels,
              MAX(report_date) AS report_date,
              MAX(ingested_at) AS ingested_at
            FROM fact_kpa_shipping_movement
            """
        )
        if df.empty:
            return {"rows": 0, "report_date": None, "vessels": 0}
        r = df.iloc[0]
        return {
            "rows": int(r.get("rows") or 0),
            "vessels": int(r.get("vessels") or 0),
            "report_date": str(r.get("report_date"))[:10] if r.get("report_date") is not None else None,
            "ingested_at": str(r.get("ingested_at")) if r.get("ingested_at") is not None else None,
        }

    def ingest_logs(self, limit: int = 20) -> pd.DataFrame:
        if not self.table_exists("fact_kpa_ingest_log"):
            return pd.DataFrame()
        return self.qdf(
            "SELECT * FROM fact_kpa_ingest_log ORDER BY ingested_at DESC NULLS LAST LIMIT :n",
            {"n": limit},
        )

    def ingest_upload(
        self,
        file_bytes: bytes,
        filename: str,
        source_url: str = "https://kpa.co.ke/ShippingMovement",
    ) -> dict[str, Any]:
        self.ensure_schema()
        from ingest_kpa_shipping_movement import ingest_file

        data_dir = self._ing_path / "data" / "kpa"
        data_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in filename) or "kpa.docx"
        if not safe.lower().endswith(".docx"):
            safe += ".docx"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = data_dir / f"{stamp}_{safe}"
        dest.write_bytes(file_bytes)
        return ingest_file(dest, source_url=source_url, engine=self.engine)

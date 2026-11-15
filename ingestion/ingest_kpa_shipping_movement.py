"""
Ingest KPA 14-day Shipping Movement DOCX into fact_kpa_shipping_movement.

Usage:
  python ingestion/ingest_kpa_shipping_movement.py path/to/list.docx
  python ingestion/ingest_kpa_shipping_movement.py --dir ingestion/data/kpa
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_utils import get_db_uri, sa_uri  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest_kpa")

# Fuzzy header → canonical field
HEADER_MAP = {
    "vessel": "vessel_name",
    "vessel name": "vessel_name",
    "ship": "vessel_name",
    "ship name": "vessel_name",
    "name of vessel": "vessel_name",
    "name": "vessel_name",
    "voyage": "voyage",
    "voy": "voyage",
    "voyage no": "voyage",
    "voyage no.": "voyage",
    "agent": "agent",
    "shipping agent": "agent",
    "ships agent": "agent",
    "eta": "eta",
    "e.t.a": "eta",
    "e.t.a.": "eta",
    "expected arrival": "eta",
    "arrival": "eta",
    "etd": "etd",
    "e.t.d": "etd",
    "e.t.d.": "etd",
    "departure": "etd",
    "berth": "berth",
    "berth no": "berth",
    "berth no.": "berth",
    "jetty": "berth",
    "cargo": "cargo",
    "cargo type": "cargo",
    "commodity": "cargo",
    "loa": "loa_m",
    "l.o.a": "loa_m",
    "length": "loa_m",
    "draft": "draft_m",
    "draught": "draft_m",
    "grt": "grt",
    "gt": "grt",
    "flag": "flag",
    "nationality": "flag",
    "from": "origin",
    "origin": "origin",
    "last port": "origin",
    "to": "destination",
    "destination": "destination",
    "next port": "destination",
    "status": "movement_type",
    "movement": "movement_type",
    "remarks": "movement_type",
}


def _norm_header(h: str) -> str:
    s = re.sub(r"\s+", " ", (h or "").strip().lower())
    s = s.replace("\n", " ")
    return s


def _parse_date_loose(val: Any) -> Optional[datetime]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, date) and not isinstance(val, datetime):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    s = str(val).strip()
    if not s or s in ("-", "—", "n/a", "N/A", "TBA", "tba"):
        return None
    for fmt in (
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d.%m.%y",
        "%d/%m/%y",
    ):
        try:
            dt = datetime.strptime(s[:16].strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    ts = pd.to_datetime(s, dayfirst=True, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def _to_float(val: Any) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def extract_report_date(path: Path, doc_text: str = "") -> Optional[date]:
    name = path.stem
    # 14 DAYS LIST 23.03.2026 / 23-03-2026 / 2026-03-23
    for pat in (
        r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})",
        r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
    ):
        m = re.search(pat, name) or re.search(pat, doc_text[:500])
        if not m:
            continue
        g = m.groups()
        try:
            if len(g[0]) == 4:
                return date(int(g[0]), int(g[1]), int(g[2]))
            return date(int(g[2]), int(g[1]), int(g[0]))
        except ValueError:
            continue
    return None


def parse_docx(path: Path) -> tuple[list[dict[str, Any]], Optional[date], str]:
    try:
        from docx import Document
    except ImportError as exc:
        raise SystemExit("Install python-docx: pip install python-docx") from exc

    raw = path.read_bytes()
    content_hash = hashlib.sha256(raw).hexdigest()
    doc = Document(str(path))
    paras = "\n".join(p.text for p in doc.paragraphs if p.text)
    report_date = extract_report_date(path, paras)

    rows: list[dict[str, Any]] = []
    for table in doc.tables:
        grid = [[(c.text or "").strip() for c in r.cells] for r in table.rows]
        if len(grid) < 2:
            continue
        # find header row (first non-empty with vessel-like word)
        header_idx = 0
        for i, line in enumerate(grid[:5]):
            joined = " ".join(line).lower()
            if any(k in joined for k in ("vessel", "ship", "eta", "berth", "voyage")):
                header_idx = i
                break
        headers_raw = grid[header_idx]
        # de-dupe empty headers
        canon: list[Optional[str]] = []
        for h in headers_raw:
            key = HEADER_MAP.get(_norm_header(h))
            if key is None:
                # partial contains
                nh = _norm_header(h)
                for k, v in HEADER_MAP.items():
                    if k in nh or nh in k:
                        key = v
                        break
            canon.append(key)

        if not any(canon):
            continue

        for line in grid[header_idx + 1 :]:
            if not any(x.strip() for x in line):
                continue
            rec: dict[str, Any] = {
                "source_file": path.name,
                "content_hash": content_hash,
                "raw_line": " | ".join(line),
            }
            for col_i, field in enumerate(canon):
                if field is None or col_i >= len(line):
                    continue
                val = line[col_i]
                if not val:
                    continue
                if field in rec and rec[field]:
                    continue
                rec[field] = val
            if not rec.get("vessel_name"):
                # first non-empty cell fallback
                for cell in line:
                    if cell and not re.match(r"^\d+$", cell):
                        rec["vessel_name"] = cell
                        break
            if not rec.get("vessel_name"):
                continue
            rows.append(rec)

    return rows, report_date, content_hash


def normalize_rows(
    rows: list[dict[str, Any]],
    report_date: Optional[date],
    source_url: str = "",
) -> pd.DataFrame:
    out = []
    for r in rows:
        eta = _parse_date_loose(r.get("eta"))
        etd = _parse_date_loose(r.get("etd"))
        out.append(
            {
                "report_date": report_date,
                "vessel_name": (r.get("vessel_name") or "").strip()[:200] or None,
                "voyage": (str(r.get("voyage") or "").strip() or None),
                "agent": (str(r.get("agent") or "").strip() or None),
                "eta": eta,
                "etd": etd,
                "berth": (str(r.get("berth") or "").strip() or None),
                "cargo": (str(r.get("cargo") or "").strip() or None),
                "loa_m": _to_float(r.get("loa_m")),
                "draft_m": _to_float(r.get("draft_m")),
                "grt": _to_float(r.get("grt")),
                "flag": (str(r.get("flag") or "").strip() or None),
                "movement_type": (str(r.get("movement_type") or "").strip() or None),
                "origin": (str(r.get("origin") or "").strip() or None),
                "destination": (str(r.get("destination") or "").strip() or None),
                "raw_line": r.get("raw_line"),
                "source_url": source_url or None,
                "source_file": r.get("source_file"),
                "content_hash": r.get("content_hash"),
            }
        )
    return pd.DataFrame(out)


def upsert_df(engine, df: pd.DataFrame, report_date: Optional[date], content_hash: str, source_file: str) -> int:
    if df.empty:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO fact_kpa_ingest_log (report_date, source_file, content_hash, row_count, status, message)
                    VALUES (:rd, :sf, :ch, 0, 'EMPTY', 'No table rows parsed')
                    """
                ),
                {"rd": report_date, "sf": source_file, "ch": content_hash},
            )
        return 0

    # delete same file hash to make re-upload idempotent
    with engine.begin() as conn:
        if content_hash:
            conn.execute(
                text("DELETE FROM fact_kpa_shipping_movement WHERE content_hash = :h"),
                {"h": content_hash},
            )
        # also clear same report_date if provided (latest wins)
        if report_date is not None:
            conn.execute(
                text("DELETE FROM fact_kpa_shipping_movement WHERE report_date = :d AND content_hash <> :h"),
                {"d": report_date, "h": content_hash or ""},
            )

        cols = [
            "report_date",
            "vessel_name",
            "voyage",
            "agent",
            "eta",
            "etd",
            "berth",
            "cargo",
            "loa_m",
            "draft_m",
            "grt",
            "flag",
            "movement_type",
            "origin",
            "destination",
            "raw_line",
            "source_url",
            "source_file",
            "content_hash",
        ]
        use = df[[c for c in cols if c in df.columns]].copy()
        n = 0
        for rec in use.to_dict(orient="records"):
            conn.execute(
                text(
                    f"""
                    INSERT INTO fact_kpa_shipping_movement ({", ".join(cols)})
                    VALUES ({", ".join(":" + c for c in cols)})
                    """
                ),
                {c: rec.get(c) for c in cols},
            )
            n += 1
        conn.execute(
            text(
                """
                INSERT INTO fact_kpa_ingest_log (report_date, source_file, content_hash, row_count, status, message)
                VALUES (:rd, :sf, :ch, :n, 'OK', 'ingested')
                """
            ),
            {"rd": report_date, "sf": source_file, "ch": content_hash, "n": n},
        )
    return n


def ingest_file(path: Path, source_url: str = "", engine=None) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    eng = engine or create_engine(sa_uri(get_db_uri()), pool_pre_ping=True)
    rows, report_date, content_hash = parse_docx(path)
    df = normalize_rows(rows, report_date, source_url=source_url)
    n = upsert_df(eng, df, report_date, content_hash, path.name)
    log.info("Ingested %s rows from %s (report_date=%s)", n, path.name, report_date)
    return {
        "file": path.name,
        "rows": n,
        "report_date": str(report_date) if report_date else None,
        "content_hash": content_hash,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest KPA shipping movement DOCX")
    ap.add_argument("paths", nargs="*", type=Path, help="DOCX file(s)")
    ap.add_argument("--dir", type=Path, help="Directory of DOCX files")
    ap.add_argument("--url", default="", help="Optional source URL attribution")
    ap.add_argument("--init", action="store_true", help="Ensure schema first")
    args = ap.parse_args(argv)

    if args.init:
        from init_kpa_and_live_feeds import main as init_main

        init_main()

    files: list[Path] = list(args.paths or [])
    if args.dir:
        files.extend(sorted(args.dir.glob("*.docx")))
        files.extend(sorted(args.dir.glob("*.DOCX")))
    if not files:
        log.error("No DOCX files provided")
        return 2

    eng = create_engine(sa_uri(get_db_uri()), pool_pre_ping=True)
    # ensure tables
    try:
        from init_kpa_and_live_feeds import main as init_main

        init_main()
    except Exception as exc:  # noqa: BLE001
        log.warning("init: %s", exc)

    total = 0
    for f in files:
        try:
            res = ingest_file(f, source_url=args.url, engine=eng)
            total += int(res["rows"])
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed %s: %s", f, exc)
    log.info("Done. total rows=%s", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

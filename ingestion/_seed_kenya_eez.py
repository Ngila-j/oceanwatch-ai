"""Seed Kenya EEZ Phase 11 schema + intelligence; probe table counts."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_INGESTION = Path(__file__).resolve().parent
_ROOT = _INGESTION.parent
if str(_INGESTION) not in sys.path:
    sys.path.insert(0, str(_INGESTION))

OUT = _ROOT / "_kenya_eez_seed_out.txt"

TABLES = [
    "data_freshness",
    "spatial_intelligence",
    "oceanwatch_events",
    "risk_scores",
    "data_provenance",
    "fact_wio_intelligence_index",
    "fact_port_metrics",
    "fact_ocean_conditions",
]


def main() -> int:
    lines: list[str] = []
    lines.append(f"Kenya EEZ seed @ {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    try:
        import init_phase11_complete as init_mod

        lines.append(">>> init_phase11_complete.main()")
        init_mod.main()
        lines.append("init OK")
    except Exception:
        lines.append("init FAILED")
        lines.append(traceback.format_exc())
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 1

    try:
        import run_phase11_intelligence as run_mod

        lines.append(">>> run_phase11_intelligence.run()")
        run_mod.run()
        lines.append("run OK")
    except Exception:
        lines.append("run FAILED")
        lines.append(traceback.format_exc())
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 1

    try:
        from db_utils import pg_connection, qdf

        lines.append("")
        lines.append("=== table counts ===")
        with pg_connection() as con:
            for t in TABLES:
                try:
                    df = qdf(con, f"SELECT COUNT(*) AS n FROM public.{t}")
                    n = int(df.iloc[0]["n"]) if df is not None and not df.empty else -1
                    lines.append(f"{t}: {n}")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{t}: ERROR {exc}")
                    try:
                        con.rollback()
                    except Exception:
                        pass
    except Exception:
        lines.append("probe FAILED")
        lines.append(traceback.format_exc())
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 1

    lines.append("")
    lines.append("DONE")
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

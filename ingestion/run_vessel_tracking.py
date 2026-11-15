"""
Vessel Tracking module runner
=============================

Orchestrates Kenya EEZ vessel tracking pipeline:

  1. Ensure Phase 12 maritime schema
  2. Seed sample AIS if fact_ais_positions is empty (optional --seed-ais)
  3. Build profiles, track points, geofence events, behaviour scores (Phase 12)
  4. Optional vessel anomaly ML (--anomalies)

Usage:
  python ingestion/run_vessel_tracking.py
  python ingestion/run_vessel_tracking.py --seed-ais
  python ingestion/run_vessel_tracking.py --anomalies
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ING = Path(__file__).resolve().parent
for p in (str(ING), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("vessel_tracking")


def _count(con, table: str) -> int:
    try:
        row = con.execute(f"SELECT COUNT(*) FROM public.{table}").fetchone()
        return int(row[0] or 0)
    except Exception:  # noqa: BLE001
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        return -1


def run(*, seed_ais: bool = False, anomalies: bool = False) -> dict:
    summary: dict = {}

    # 1) Schema
    logger.info("=== Vessel Tracking: schema ===")
    try:
        from init_phase12_maritime import main as ensure_schema

        ensure_schema()
        summary["schema"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.exception("schema failed: %s", exc)
        summary["schema"] = f"error: {exc}"
        return summary

    # 2) Optional AIS seed
    if seed_ais:
        logger.info("=== Vessel Tracking: seed AIS sample ===")
        try:
            from seed_ais_sample import seed_ais

            seed_ais()
            summary["ais_seed"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIS seed failed: %s", exc)
            summary["ais_seed"] = f"error: {exc}"
    else:
        # Auto-seed only when AIS empty
        try:
            from db_utils import pg_connection

            with pg_connection() as con:
                n = _count(con, "fact_ais_positions")
                summary["fact_ais_positions"] = n
                if n == 0:
                    logger.info("AIS empty — seeding sample positions")
                    from seed_ais_sample import seed_ais

                    seed_ais()
                    summary["ais_seed"] = "auto"
        except Exception as exc:  # noqa: BLE001
            logger.warning("AIS probe/seed skipped: %s", exc)
            summary["ais_seed"] = f"skip: {exc}"

    # 3) Phase 12 compute
    logger.info("=== Vessel Tracking: phase12 maritime ===")
    try:
        import run_phase12_maritime as p12

        p12.run()
        summary["phase12"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.exception("phase12 failed: %s", exc)
        summary["phase12"] = f"error: {exc}"

    # 4) Port activity (Mombasa arrivals / metrics) — seed if empty
    logger.info("=== Vessel Tracking: port activity ===")
    try:
        from db_utils import pg_connection

        with pg_connection() as con:
            n_pa = _count(con, "fact_port_activity")
            n_pm = _count(con, "fact_port_metrics")
        if n_pa == 0 or n_pm == 0:
            import seed_port_activity as spa

            if hasattr(spa, "seed_port_activity"):
                spa.seed_port_activity()
            elif hasattr(spa, "main"):
                spa.main()
            elif hasattr(spa, "run"):
                spa.run()
            else:
                raise RuntimeError("seed_port_activity entrypoint missing")
            summary["port_seed"] = "auto"
        else:
            summary["port_seed"] = f"skip existing activity={n_pa} metrics={n_pm}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("port seed skipped: %s", exc)
        summary["port_seed"] = f"skip: {exc}"

    # 5) Optional anomalies
    if anomalies:
        logger.info("=== Vessel Tracking: anomaly ML ===")
        try:
            import ml_vessel_anomaly as anom

            if hasattr(anom, "run_pipeline"):
                anom.run_pipeline()
            elif hasattr(anom, "run"):
                anom.run()
            else:
                raise RuntimeError("ml_vessel_anomaly has no run entrypoint")
            summary["anomalies"] = "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("anomaly job failed: %s", exc)
            summary["anomalies"] = f"error: {exc}"

    # 5) Counts
    try:
        from db_utils import pg_connection

        tables = [
            "fact_ais_positions",
            "dim_vessels_maritime",
            "fact_vessel_profiles",
            "fact_vessel_track_points",
            "fact_geofence_events",
            "fact_vessel_behaviour_scores",
            "dim_geofences",
            "fact_vessel_anomalies",
            "fact_port_activity",
            "fact_port_metrics",
            "fact_gfw_fishing_effort",
            "fact_fishing_effort",
        ]
        with pg_connection() as con:
            for t in tables:
                summary[f"count_{t}"] = _count(con, t)
                logger.info("COUNT %s=%s", t, summary[f"count_{t}"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("count probe failed: %s", exc)

    logger.info("=== Vessel Tracking done === %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OceanWatch vessel tracking pipeline")
    p.add_argument(
        "--seed-ais",
        action="store_true",
        help="Force re-seed sample AIS positions",
    )
    p.add_argument(
        "--anomalies",
        action="store_true",
        help="Also run ml_vessel_anomaly pipeline",
    )
    args = p.parse_args(argv)
    summary = run(seed_ais=args.seed_ais, anomalies=args.anomalies)
    failed = any(
        str(v).startswith("error")
        for k, v in summary.items()
        if k in ("schema", "phase12")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

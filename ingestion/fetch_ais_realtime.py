"""
OceanWatch AI — Hybrid live AIS via AISStream.io

Strategy:
  - Subscribe to WORLD stream (reliable message flow)
  - Keep only positions inside Kenya / Western Indian Ocean box (client-side)
  - Cap max messages processed so DAG runs stay bounded
  - Default listen window: 180s (override with AIS_COLLECT_SECONDS)

Writes matches to fact_ais_positions with source='AISSTREAM'.
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import duckdb
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent / ".env")
API_KEY = (os.getenv("AISSTREAM_API_KEY") or os.getenv("AIS_API_KEY") or "").strip()

# How long to listen
COLLECT_SECONDS = int(os.getenv("AIS_COLLECT_SECONDS", "180"))

# Stop early after this many raw messages (protects CPU on the global firehose)
MAX_RAW_MESSAGES = int(os.getenv("AIS_MAX_RAW", "15000"))

# Kenya / Western Indian Ocean keep-filter
KE_LAT_MIN, KE_LAT_MAX = -6.0, 3.0
KE_LON_MIN, KE_LON_MAX = 38.0, 46.0


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def ship_type_to_label(code) -> str:
    try:
        c = int(code)
    except Exception:
        return "OTHER"
    if c == 30:
        return "FISHING"
    if 60 <= c <= 69:
        return "PASSENGER"
    if 70 <= c <= 79:
        return "CARGO"
    if 80 <= c <= 89:
        return "TANKER"
    return "OTHER"


def extract_position(msg: dict):
    meta = msg.get("MetaData") or {}
    message = msg.get("Message") or {}
    pos = (
        message.get("PositionReport")
        or message.get("StandardClassBPositionReport")
        or message.get("ExtendedClassBPositionReport")
        or {}
    )
    lat = pos.get("Latitude", meta.get("latitude"))
    lon = pos.get("Longitude", meta.get("longitude"))
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except Exception:
        return None

    mmsi = meta.get("MMSI") or pos.get("UserID")
    name = (meta.get("ShipName") or "").strip() or (f"MMSI {mmsi}" if mmsi else "UNKNOWN")
    ship_type = meta.get("Type") or meta.get("ship_type") or pos.get("ShipType")
    sog = pos.get("Sog", meta.get("sog"))
    cog = pos.get("Cog", meta.get("cog"))
    heading = pos.get("TrueHeading")
    if heading == 511:
        heading = None

    return {
        "mmsi": str(mmsi) if mmsi is not None else None,
        "vessel_name": name[:100],
        "vessel_type": ship_type_to_label(ship_type),
        "flag_country": None,
        "latitude": lat_f,
        "longitude": lon_f,
        "sog": float(sog) if sog is not None else None,
        "cog": float(cog) if cog is not None else None,
        "heading": float(heading) if heading is not None else None,
        "nav_status": str(pos.get("NavigationalStatus")) if pos.get("NavigationalStatus") is not None else None,
        "event_time": datetime.now(timezone.utc).replace(tzinfo=None),
        "source": "AISSTREAM",
        "created_at": datetime.utcnow(),
    }


def in_kenya_box(lat: float, lon: float) -> bool:
    return KE_LAT_MIN <= lat <= KE_LAT_MAX and KE_LON_MIN <= lon <= KE_LON_MAX


def collect_ais(api_key: str, seconds: int) -> list:
    from websocket import WebSocketApp

    records = []
    stats = {"raw": 0, "parsed": 0, "kenya": 0}
    stop_flag = {"stop": False}
    lock = threading.Lock()

    def on_message(ws, message):
        if stop_flag["stop"]:
            return

        with lock:
            stats["raw"] += 1
            raw_n = stats["raw"]
            if raw_n <= 2:
                logger.info(f"RAW #{raw_n}: {message[:300]}")
            elif raw_n % 500 == 0:
                logger.info(
                    f"raw={stats['raw']} parsed={stats['parsed']} kenya={stats['kenya']}"
                )
            if raw_n >= MAX_RAW_MESSAGES:
                logger.info(f"Reached MAX_RAW_MESSAGES={MAX_RAW_MESSAGES}; stopping")
                stop_flag["stop"] = True
                try:
                    ws.close()
                except Exception:
                    pass
                return

        try:
            msg = json.loads(message)
        except Exception:
            return

        if "error" in msg or msg.get("MessageType") == "ErrorMessage":
            logger.error(f"AISStream error: {msg}")
            return

        row = extract_position(msg)
        if not row:
            return

        with lock:
            stats["parsed"] += 1

        if not in_kenya_box(row["latitude"], row["longitude"]):
            return

        with lock:
            records.append(row)
            stats["kenya"] += 1
            if stats["kenya"] <= 5 or stats["kenya"] % 10 == 0:
                logger.info(
                    f"KENYA HIT #{stats['kenya']}: {row['vessel_name']} "
                    f"({row['latitude']:.3f}, {row['longitude']:.3f}) sog={row['sog']}"
                )

    def on_error(ws, error):
        logger.error(f"WebSocket error: {error}")

    def on_close(ws, code, msg):
        logger.info(f"WebSocket closed code={code}")

    def on_open(ws):
        # Hybrid: WORLD subscribe for reliable flow; filter Kenya client-side
        sub = {
            "APIKey": api_key,
            "BoundingBoxes": [[[-90.0, -180.0], [90.0, 180.0]]],
        }
        ws.send(json.dumps(sub))
        logger.info(
            f"Hybrid mode: WORLD subscribe, Kenya filter "
            f"lat[{KE_LAT_MIN},{KE_LAT_MAX}] lon[{KE_LON_MIN},{KE_LON_MAX}] "
            f"for {seconds}s (max_raw={MAX_RAW_MESSAGES})"
        )

    ws = WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    t = threading.Thread(
        target=ws.run_forever,
        kwargs={"ping_interval": 20, "ping_timeout": 10},
        daemon=True,
    )
    t.start()

    t0 = time.time()
    while time.time() - t0 < seconds and t.is_alive() and not stop_flag["stop"]:
        time.sleep(1)

    try:
        ws.close()
    except Exception:
        pass
    time.sleep(1)

    logger.info(
        f"Finished: raw={stats['raw']} parsed={stats['parsed']} kenya={stats['kenya']}"
    )
    return list(records)


def write_to_postgres(records: list):
    if not records:
        logger.warning(
            "No Kenya/WIO AIS hits this window "
            "(coverage can be sparse — SAMPLE data remains available)"
        )
        return

    df = pd.DataFrame(records)
    df.insert(0, "position_id", range(1, len(df) + 1))

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_ais_positions (
            position_id INTEGER,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            sog DOUBLE,
            cog DOUBLE,
            heading DOUBLE,
            nav_status VARCHAR,
            event_time TIMESTAMP,
            source VARCHAR,
            created_at TIMESTAMP
        );
    """)
    con.register("ais_df", df)
    con.execute("INSERT INTO pg.public.fact_ais_positions SELECT * FROM ais_df;")
    logger.info(f"Inserted {len(df)} AISSTREAM rows into fact_ais_positions")
    con.close()


def main():
    logger.info("=== Hybrid Live AIS Ingestion (WORLD → Kenya filter) ===")
    if not API_KEY:
        raise ValueError("AISSTREAM_API_KEY not set in ingestion/.env")

    logger.info(f"Collect window: {COLLECT_SECONDS}s | max raw: {MAX_RAW_MESSAGES}")
    records = collect_ais(API_KEY, COLLECT_SECONDS)
    write_to_postgres(records)
    logger.info("=== Hybrid AIS ingestion completed ===")


if __name__ == "__main__":
    main()
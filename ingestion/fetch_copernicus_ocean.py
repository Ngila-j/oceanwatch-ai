import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import copernicusmarine
import xarray as xr

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Try multiple possible locations for the .env file
possible_env_paths = [
    Path(__file__).parent / ".env",
    Path("/opt/airflow/ingestion/.env"),
    Path("/opt/airflow/data/.env"),
]

env_loaded = False
for env_path in possible_env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded credentials from {env_path}")
        env_loaded = True
        break

if not env_loaded:
    logger.warning("No .env file found in expected locations")

USERNAME = os.getenv("COPERNICUS_USERNAME")
PASSWORD = os.getenv("COPERNICUS_PASSWORD")

logger.info(f"USERNAME set: {bool(USERNAME)}, PASSWORD set: {bool(PASSWORD)}")

# Western Indian Ocean / Kenya EEZ bounding box (Mombasa focused)
MIN_LON, MAX_LON = 39.0, 45.0
MIN_LAT, MAX_LAT = -5.0, 2.0

OUTPUT_DIR = Path("/opt/airflow/data/raw/copernicus")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def fetch_sst(start_date: str, end_date: str) -> Path:
    """Fetch Sea Surface Temperature (thetao) for the region."""
    logger.info("Fetching SST (thetao) from Copernicus Marine...")
    output_file = OUTPUT_DIR / f"sst_{start_date}_{end_date}.nc"

    copernicusmarine.subset(
        dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
        variables=["thetao"],
        minimum_longitude=MIN_LON,
        maximum_longitude=MAX_LON,
        minimum_latitude=MIN_LAT,
        maximum_latitude=MAX_LAT,
        start_datetime=f"{start_date}T00:00:00",
        end_datetime=f"{end_date}T23:59:59",
        minimum_depth=0,
        maximum_depth=1,
        output_filename=str(output_file.name),
        output_directory=str(OUTPUT_DIR),
        username=USERNAME,
        password=PASSWORD,
        force_download=True,
    )
    logger.info(f"SST saved to {output_file}")
    return output_file


def fetch_chlorophyll(start_date: str, end_date: str) -> Path:
    """Fetch Chlorophyll-a for the region."""
    logger.info("Fetching Chlorophyll-a from Copernicus Marine...")
    output_file = OUTPUT_DIR / f"chl_{start_date}_{end_date}.nc"

    copernicusmarine.subset(
        dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        variables=["CHL"],
        minimum_longitude=MIN_LON,
        maximum_longitude=MAX_LON,
        minimum_latitude=MIN_LAT,
        maximum_latitude=MAX_LAT,
        start_datetime=f"{start_date}T00:00:00",
        end_datetime=f"{end_date}T23:59:59",
        output_filename=str(output_file.name),
        output_directory=str(OUTPUT_DIR),
        username=USERNAME,
        password=PASSWORD,
        force_download=True,
    )
    logger.info(f"Chlorophyll saved to {output_file}")
    return output_file


def load_summary_to_postgres(nc_path: Path, variable: str, table_name: str):
    """Create a simple tabular summary and load into Postgres."""
    logger.info(f"Creating summary for {variable} -> {table_name}")
    ds = xr.open_dataset(nc_path)

    if "depth" in ds.dims:
        ds = ds.isel(depth=0)

    da = ds[variable]

    df = da.mean(dim=["latitude", "longitude"]).to_dataframe().reset_index()
    df = df.rename(columns={variable: f"{variable}_mean"})
    df["source_file"] = nc_path.name
    df["loaded_at"] = datetime.utcnow()

    engine = create_engine(get_db_uri())
    df.to_sql(table_name, engine, if_exists="append", index=False)
    logger.info(f"Loaded {len(df)} summary rows into {table_name}")


def main():
    logger.info("=== Copernicus Marine Ingestion Started ===")
    start = datetime.utcnow()

    if not USERNAME or not PASSWORD:
        raise ValueError("COPERNICUS_USERNAME or COPERNICUS_PASSWORD not set in .env")

    end_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")

    logger.info(f"Date range: {start_date} -> {end_date}")
    logger.info(f"Bounding box: lon [{MIN_LON}, {MAX_LON}], lat [{MIN_LAT}, {MAX_LAT}]")

    # 1. SST
    sst_file = fetch_sst(start_date, end_date)
    load_summary_to_postgres(sst_file, "thetao", "raw_sst_daily")

    # 2. Chlorophyll
    chl_file = fetch_chlorophyll(start_date, end_date)
    load_summary_to_postgres(chl_file, "CHL", "raw_chl_daily")

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"=== Copernicus ingestion completed in {duration:.1f}s ===")


if __name__ == "__main__":
    main()
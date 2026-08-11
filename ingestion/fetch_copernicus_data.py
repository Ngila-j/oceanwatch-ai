import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
import copernicusmarine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration – Western Indian Ocean / Kenya EEZ / Mombasa focus
# ------------------------------------------------------------------
BBOX = {
    "minimum_longitude": 39.0,   # west of Mombasa
    "maximum_longitude": 45.0,   # east into the Indian Ocean
    "minimum_latitude": -5.5,    # south of Kenya
    "maximum_latitude": 2.0,     # north of Kenya
}

# Small recent window so the first download stays light
END_DATE = datetime.utcnow().date()
START_DATE = END_DATE - timedelta(days=3)

OUTPUT_DIR = Path("/opt/airflow/data/raw/copernicus")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"

def login_copernicus():
    """Login using credentials from environment or .env file."""
    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")

    if not username or not password:
        # fallback: try reading the .env file we created
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("COPERNICUS_USERNAME="):
                    username = line.split("=", 1)[1].strip()
                elif line.startswith("COPERNICUS_PASSWORD="):
                    password = line.split("=", 1)[1].strip()

    if not username or not password:
        raise ValueError("Copernicus credentials not found. Set COPERNICUS_USERNAME and COPERNICUS_PASSWORD.")

    copernicusmarine.login(username=username, password=password, force_overwrite=True)
    logger.info("Successfully logged in to Copernicus Marine")

def fetch_sst():
    """Fetch Sea Surface Temperature (thetao) for the region."""
    logger.info("Fetching SST (thetao) from Copernicus...")
    output_file = OUTPUT_DIR / f"sst_{START_DATE}_{END_DATE}.nc"

    copernicusmarine.subset(
        dataset_id="cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
        variables=["thetao"],
        minimum_longitude=BBOX["minimum_longitude"],
        maximum_longitude=BBOX["maximum_longitude"],
        minimum_latitude=BBOX["minimum_latitude"],
        maximum_latitude=BBOX["maximum_latitude"],
        start_datetime=f"{START_DATE}T00:00:00",
        end_datetime=f"{END_DATE}T23:59:59",
        minimum_depth=0,
        maximum_depth=1,          # surface only
        output_filename=str(output_file.name),
        output_directory=str(OUTPUT_DIR),
        force_download=True,
    )
    logger.info(f"SST saved to {output_file}")
    return output_file

def fetch_chlorophyll():
    """Fetch Chlorophyll-a (simplified global product)."""
    logger.info("Fetching Chlorophyll-a from Copernicus...")
    output_file = OUTPUT_DIR / f"chl_{START_DATE}_{END_DATE}.nc"

    try:
        copernicusmarine.subset(
            dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
            variables=["CHL"],
            minimum_longitude=BBOX["minimum_longitude"],
            maximum_longitude=BBOX["maximum_longitude"],
            minimum_latitude=BBOX["minimum_latitude"],
            maximum_latitude=BBOX["maximum_latitude"],
            start_datetime=f"{START_DATE}T00:00:00",
            end_datetime=f"{END_DATE}T23:59:59",
            output_filename=str(output_file.name),
            output_directory=str(OUTPUT_DIR),
            force_download=True,
        )
        logger.info(f"Chlorophyll saved to {output_file}")
        return output_file
    except Exception as e:
        logger.warning(f"Chlorophyll download failed (dataset may have changed): {e}")
        return None

def netcdf_to_summary_df(nc_path: Path, value_col: str) -> pd.DataFrame:
    """Convert a NetCDF file to a simple daily summary DataFrame."""
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    # Take the first (and usually only) data variable
    data_var = list(ds.data_vars)[0]
    da = ds[data_var]

    # Daily mean over the spatial domain
    daily = da.mean(dim=[d for d in da.dims if d not in ("time",)]).to_dataframe(name=value_col)
    daily = daily.reset_index()
    daily["source_file"] = nc_path.name
    return daily

def store_summaries(dfs: list[pd.DataFrame]):
    if not dfs:
        logger.warning("No dataframes to store")
        return

    df = pd.concat(dfs, ignore_index=True)
    engine = create_engine(get_db_uri())
    df.to_sql("raw_ocean_conditions", engine, if_exists="append", index=False)
    logger.info(f"Stored {len(df)} summary rows into raw_ocean_conditions")

def main():
    logger.info("=== Copernicus Marine Ingestion Started ===")
    start = datetime.utcnow()

    login_copernicus()

    sst_file = fetch_sst()
    chl_file = fetch_chlorophyll()

    summaries = []
    if sst_file and sst_file.exists():
        summaries.append(netcdf_to_summary_df(sst_file, "sst_celsius"))
    if chl_file and chl_file.exists():
        summaries.append(netcdf_to_summary_df(chl_file, "chlorophyll_mg_m3"))

    store_summaries(summaries)

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"=== Copernicus ingestion finished in {duration:.1f}s ===")

if __name__ == "__main__":
    main()
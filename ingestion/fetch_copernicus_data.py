import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import duckdb
from dotenv import load_dotenv
import copernicusmarine
import xarray as xr

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

USERNAME = os.getenv("COPERNICUS_USERNAME")
PASSWORD = os.getenv("COPERNICUS_PASSWORD")

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
        output_filename=str(output_file.name),
        output_directory=str(OUTPUT_DIR),
        username=USERNAME,
        password=PASSWORD,
    )
    logger.info(f"SST saved to {output_file}")
    return output_file


def fetch_chlorophyll(start_date: str, end_date: str) -> Path:
    logger.info("Fetching Chlorophyll (CHL) from Copernicus Marine...")
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
    )
    logger.info(f"Chlorophyll saved to {output_file}")
    return output_file


def load_summary_to_postgres(nc_path: Path, variable: str, table_name: str) -> None:
    logger.info(f"Creating summary for {variable} -> {table_name}")

    if not nc_path.exists():
        candidates = list(OUTPUT_DIR.glob(f"*{nc_path.stem}*.nc")) + list(OUTPUT_DIR.glob("*.nc"))
        if candidates:
            nc_path = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
        else:
            logger.error(f"NetCDF file not found: {nc_path}")
            return

    ds = xr.open_dataset(nc_path)
    data_var = variable
    if variable not in ds and variable.upper() in ds:
        data_var = variable.upper()
    if data_var not in ds:
        data_vars = list(ds.data_vars)
        if not data_vars:
            logger.error("No data variables in NetCDF")
            return
        data_var = data_vars[0]

    da = ds[data_var]
    if "depth" in da.dims:
        da = da.isel(depth=0)

    spatial_dims = [d for d in da.dims if d not in ("time",)]
    daily = da.mean(dim=spatial_dims, skipna=True) if spatial_dims else da
    df = daily.to_dataframe().reset_index()

    if variable == "thetao":
        value_col = "thetao_mean"
    else:
        value_col = "CHL_mean"

    if data_var in df.columns:
        df = df.rename(columns={data_var: value_col})
    else:
        for c in df.columns:
            if c != "time" and pd.api.types.is_numeric_dtype(df[c]):
                df = df.rename(columns={c: value_col})
                break

    if "time" not in df.columns:
        for c in df.columns:
            if "time" in c.lower() or "date" in c.lower():
                df = df.rename(columns={c: "time"})
                break

    df["source_file"] = nc_path.name
    df["loaded_at"] = datetime.utcnow()
    keep = [c for c in ["time", value_col, "source_file", "loaded_at"] if c in df.columns]
    df = df[keep].dropna()

    db_uri = get_db_uri()
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{db_uri}' AS pg (TYPE POSTGRES);")
    con.register("tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE pg.public.{table_name} AS SELECT * FROM tmp_df;")
    con.close()
    logger.info(f"Loaded {len(df)} summary rows into {table_name}")


def main():
    logger.info("=== Copernicus Marine Ingestion Started ===")
    start = datetime.utcnow()

    if not USERNAME or not PASSWORD:
        raise ValueError("COPERNICUS_USERNAME or COPERNICUS_PASSWORD not set in .env")

    # 90-day lookback for ML training
    end_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

    logger.info(f"Date range: {start_date} -> {end_date}")
    logger.info(f"Bounding box: lon [{MIN_LON}, {MAX_LON}], lat [{MIN_LAT}, {MAX_LAT}]")

    sst_file = fetch_sst(start_date, end_date)
    load_summary_to_postgres(sst_file, "thetao", "raw_sst_daily")

    chl_file = fetch_chlorophyll(start_date, end_date)
    load_summary_to_postgres(chl_file, "CHL", "raw_chl_daily")

    duration = (datetime.utcnow() - start).total_seconds()
    logger.info(f"=== Copernicus ingestion completed in {duration:.1f}s ===")


if __name__ == "__main__":
    main()
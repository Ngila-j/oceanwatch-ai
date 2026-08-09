import os
import requests
import pandas as pd
from sqlalchemy import create_engine

def fetch_noaa_tide_sample():
    """Fetches sample water level/tide data from NOAA public API endpoints."""
    print("Fetching sample ocean/tide data...")
    url = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?begin_date=20260101&end_date=20260102&station=8518750&product=water_level&datum=MLLW&time_zone=gmt&units=metric&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                df = pd.DataFrame(data)
                print(f"Successfully fetched {len(df)} records from NOAA.")
                return df
    except Exception as e:
        print(f"API notice: Network or endpoint constraint encountered ({e}).")
            
    print("Using local backup structure for pipeline testing.")
    return pd.DataFrame({
        't': ['2026-06-01 00:00', '2026-06-01 01:00'],
        'v': [1.23, 1.45],
        's': ['0.015', '0.014']
    })

def store_in_postgres(df):
    """Loads raw ingestion data directly into the PostgreSQL/PostGIS container."""
    db_uri = "postgresql://postgres:password@localhost:5433/oceanwatch_db"
    engine = create_engine(db_uri)
    
    # Write dataframe to table 'raw_tides' in the public schema
    df.to_sql('raw_tides', engine, if_exists='replace', index=False)
    print("Data successfully loaded into PostgreSQL table: raw_tides")

if __name__ == "__main__":
    tide_df = fetch_noaa_tide_sample()
    store_in_postgres(tide_df)
    print("Ingestion execution completed successfully.")
import os
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

def run_oceanwatch_etl():
    # Database connection string from your docker-compose environment
    db_conn_str = "postgresql+psycopg2://postgres:password@postgres:5432/oceanwatch_db"
    engine = create_engine(db_conn_str)

    print("Extracting environmental/marine data...")
    # Example dataset or API extraction logic for Oceanwatch AI
    data = {
        'station_id': ['STN_001', 'STN_002', 'STN_003'],
        'latitude': [-3.386, -4.043, -3.550],
        'longitude': [39.983, 39.668, 39.800],
        'water_temperature_c': [26.5, 28.1, 27.4],
        'salinity_psu': [35.2, 34.8, 35.0],
        'timestamp': [datetime.utcnow(), datetime.utcnow(), datetime.utcnow()]
    }
    
    df = pd.DataFrame(data)

    print("Transforming data...")
    # Clean or format data if needed
    df['status'] = 'processed'

    print("Loading data into PostgreSQL/PostGIS...")
    # Write dataframe to database table
    with engine.begin() as connection:
        df.to_sql('marine_observations', con=connection, if_exists='append', index=False)
        
        # Optional: Convert lat/long into PostGIS spatial geometry points
        connection.execute(text("""
            ALTER TABLE marine_observations 
            ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);
            
            UPDATE marine_observations 
            SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            WHERE geom IS NULL;
        >"))

    print("Oceanwatch ETL pipeline completed successfully!")

if __name__ == "__main__":
    run_oceanwatch_etl()
FROM apache/airflow:2.7.1-python3.10

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --no-cache-dir \
    pandas \
    requests \
    sqlalchemy \
    psycopg2-binary \
    duckdb \
    dbt-core \
    dbt-postgres \
    dbt-duckdb \
    copernicusmarine \
    xarray \
    netCDF4 \
    h5netcdf

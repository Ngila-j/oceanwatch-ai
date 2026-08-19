"""KMD / met ingestion interface — implement KenyaWeatherProvider when access exists."""
import logging
logger = logging.getLogger(__name__)

class WeatherProvider:
    def fetch(self, start_date, end_date, region_id="kenya_eez"):
        raise NotImplementedError

class KenyaWeatherProvider(WeatherProvider):
    def fetch(self, start_date, end_date, region_id="kenya_eez"):
        logger.info("KMD stub — no fabricated weather rows")
        return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    KenyaWeatherProvider().fetch(None, None)
"""Local tide gauge ingestion framework — partner data when available."""
import logging
logger = logging.getLogger(__name__)

def fetch(start_date, end_date, region_id="kenya_eez"):
    logger.info("Tide gauge fetch stub region=%s (awaiting partner feed)", region_id)
    return []  # no invented observations

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch(None, None)
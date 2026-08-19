"""Fisheries catch framework — only load authorized/open datasets."""
import logging
logger = logging.getLogger(__name__)

def fetch(start_date, end_date, region_id="kenya_eez"):
    logger.info(
        "Fisheries catch stub region=%s — data availability depends on authorized sources",
        region_id,
    )
    return []

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch(None, None)
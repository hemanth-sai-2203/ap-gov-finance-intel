import os
import time
import logging
import weaviate
from weaviate.classes.init import Auth, AdditionalConfig, Timeout
from app.core.config import settings

logger = logging.getLogger(__name__)

WEAVIATE_URL = settings.WEAVIATE_URL
WEAVIATE_API_KEY = settings.WEAVIATE_API_KEY
WEAVIATE_INDEX_NAME = settings.WEAVIATE_INDEX_NAME or "GovIntelDocument"


def get_weaviate_client(max_retries: int = 5, retry_delay: float = 3.0):
    """
    Returns a connected Weaviate Cloud client with automatic retries and timeout protection.
    """
    if not WEAVIATE_URL or not WEAVIATE_API_KEY:
        raise ValueError("WEAVIATE_URL and WEAVIATE_API_KEY must be set in .env")

    for attempt in range(1, max_retries + 1):
        try:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=WEAVIATE_URL,
                auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
                additional_config=AdditionalConfig(
                    timeout=Timeout(init=60, query=60, insert=120)
                ),
                skip_init_checks=True
            )
            return client
        except Exception as e:
            delay = attempt * retry_delay
            if attempt == max_retries:
                logger.error(f"Weaviate connection failed after {max_retries} attempts: {e}")
                raise e
            logger.warning(f"Weaviate connection attempt {attempt}/{max_retries} failed ({e}). Retrying in {delay:.1f}s...")
            time.sleep(delay)

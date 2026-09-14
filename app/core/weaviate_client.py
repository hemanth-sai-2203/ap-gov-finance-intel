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


_WEAVIATE_LAST_FAILED = 0
_WEAVIATE_COOLDOWN = 120  # seconds to skip Weaviate after failure


def get_weaviate_client(max_retries: int = 1, retry_delay: float = 0.5):
    """
    Returns a connected Weaviate Cloud client with fast failover and circuit breaker protection.
    """
    global _WEAVIATE_LAST_FAILED
    now = time.time()
    if now - _WEAVIATE_LAST_FAILED < _WEAVIATE_COOLDOWN:
        raise ConnectionError("Weaviate Cloud is currently in failover cooldown. Bypassing directly to PostgreSQL.")

    if not WEAVIATE_URL or not WEAVIATE_API_KEY:
        raise ValueError("WEAVIATE_URL and WEAVIATE_API_KEY must be set in .env")

    for attempt in range(1, max_retries + 1):
        try:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=WEAVIATE_URL,
                auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
                additional_config=AdditionalConfig(
                    timeout=Timeout(init=2, query=3, insert=5)
                ),
                skip_init_checks=True
            )
            return client
        except Exception as e:
            _WEAVIATE_LAST_FAILED = time.time()
            logger.warning(f"Weaviate connection failed ({e}). Circuit breaker activated.")
            raise e


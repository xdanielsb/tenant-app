import json
import logging
import redis.asyncio as redis
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

# Bump when the cached payload shape or scoping rules change so a deploy
# does not serve poisoned keys written by an older version.
CACHE_VERSION = "v2"


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for revenue lookup")

    cache_key = f"revenue:{CACHE_VERSION}:{tenant_id}:{property_id}"

    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        # Defense in depth: cached payload must belong to the requesting tenant.
        # Reaching this branch would indicate a key-construction regression.
        if data.get("tenant_id") == tenant_id:
            return data
        logger.error(
            "Tenant mismatch on cache read for key %s: cached tenant=%s, requested tenant=%s",
            cache_key, data.get("tenant_id"), tenant_id,
        )
        await redis_client.delete(cache_key)

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result

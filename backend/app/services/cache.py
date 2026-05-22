import json
import logging
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

# Bump when the cached payload shape or scoping rules change so a deploy
# does not serve poisoned keys written by an older version.
CACHE_VERSION = "v2"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.

    When both ``month`` and ``year`` are supplied, returns revenue for that
    calendar month in the property's local timezone; otherwise returns the
    all-time total.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for revenue lookup")

    if (month is None) != (year is None):
        raise ValueError("month and year must be supplied together")

    if month is not None:
        period_suffix = f":{year:04d}-{month:02d}"
    else:
        period_suffix = ""
    cache_key = f"revenue:{CACHE_VERSION}:{tenant_id}:{property_id}{period_suffix}"

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

    if month is not None:
        from app.services.reservations import calculate_monthly_revenue
        result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    else:
        from app.services.reservations import calculate_total_revenue
        result = await calculate_total_revenue(property_id, tenant_id)

    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result

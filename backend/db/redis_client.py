"""Async Redis client used for pub/sub inter-agent messaging + caching."""
from typing import Optional

import redis.asyncio as aioredis

from backend.core.config import settings
from backend.core.logging import logger

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        logger.info("Redis connection established")
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


# Channels used by the agent bus
CHANNEL_INGEST = "autocti:ingest"
CHANNEL_CORRELATE = "autocti:correlate"
CHANNEL_SCORE = "autocti:score"
CHANNEL_EXPLAIN = "autocti:explain"
CHANNEL_FEEDBACK = "autocti:feedback"

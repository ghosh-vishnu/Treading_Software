from __future__ import annotations

from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import logger


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)


def redis_available() -> bool:
    try:
        return bool(get_redis_client().ping())
    except RedisError as exc:
        logger.warning("Redis unavailable error_type=%s", type(exc).__name__)
        return False

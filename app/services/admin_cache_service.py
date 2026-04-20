from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import logger


class AdminCacheService:
    def __init__(self) -> None:
        self._client: Redis | None = None
        self._checked = False

    def _get_client(self) -> Redis | None:
        if self._checked:
            return self._client

        self._checked = True
        try:
            client = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
            client.ping()
            self._client = client
            logger.info("Admin cache connected to Redis")
        except Exception as exc:
            logger.warning("Admin cache Redis unavailable: %s", exc)
            self._client = None
        return self._client

    @staticmethod
    def _json_default(value: object):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported JSON type: {type(value)!r}")

    def get_json(self, key: str):
        client = self._get_client()
        if client is None:
            return None

        try:
            payload = client.get(key)
            if payload is None:
                return None
            return json.loads(payload)
        except (RedisError, json.JSONDecodeError):
            return None

    def set_json(self, key: str, value, ttl_seconds: int) -> None:
        client = self._get_client()
        if client is None:
            return

        try:
            payload = json.dumps(value, default=self._json_default)
            client.setex(key, ttl_seconds, payload)
        except (RedisError, TypeError):
            return

    def delete_by_prefix(self, prefix: str) -> None:
        client = self._get_client()
        if client is None:
            return

        try:
            keys = list(client.scan_iter(match=f"{prefix}*"))
            if keys:
                client.delete(*keys)
        except RedisError:
            return


admin_cache_service = AdminCacheService()

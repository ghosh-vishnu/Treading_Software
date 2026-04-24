from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import logger
from app.core.redis_client import get_redis_client


class LockUnavailableError(RuntimeError):
    """Raised when the process cannot safely coordinate an order lock."""


class LockBusyError(RuntimeError):
    """Raised when another request already owns the order lock."""


_LOCAL_LOCKS: dict[str, float] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


@dataclass
class RedisOrderLock:
    key: str
    ttl_seconds: int

    def __post_init__(self) -> None:
        self._token = uuid4().hex
        self._uses_redis = False

    def __enter__(self) -> RedisOrderLock:
        redis_key = f"lock:order:{self.key}"
        try:
            acquired = get_redis_client().set(redis_key, self._token, nx=True, ex=self.ttl_seconds)
            self._uses_redis = True
        except RedisError as exc:
            if settings.environment == "production" and settings.broker_require_redis_for_live_trading:
                raise LockUnavailableError("Redis order lock is unavailable.") from exc
            logger.warning("Falling back to process-local order lock key=%s error_type=%s", self.key, type(exc).__name__)
            acquired = self._acquire_local()

        if not acquired:
            raise LockBusyError("Duplicate order is already being processed.")
        return self

    def __exit__(self, *_: object) -> None:
        redis_key = f"lock:order:{self.key}"
        if self._uses_redis:
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            end
            return 0
            """
            try:
                get_redis_client().eval(script, 1, redis_key, self._token)
            except RedisError as exc:
                logger.warning("Failed to release Redis order lock key=%s error_type=%s", self.key, type(exc).__name__)
            return
        self._release_local()

    def _acquire_local(self) -> bool:
        expires_at = time.time() + self.ttl_seconds
        with _LOCAL_LOCKS_GUARD:
            existing_expiry = _LOCAL_LOCKS.get(self.key)
            if existing_expiry and existing_expiry > time.time():
                return False
            _LOCAL_LOCKS[self.key] = expires_at
            return True

    def _release_local(self) -> None:
        with _LOCAL_LOCKS_GUARD:
            _LOCAL_LOCKS.pop(self.key, None)

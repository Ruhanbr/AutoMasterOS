"""
Redis async client para cache — TTL padrão 300 s (5 min).

Uso:
    from app.core.redis_client import cache
    await cache.get("key")
    await cache.set("key", value, ttl=300)
    await cache.delete("key")
    await cache.delete_pattern("prefix:*")
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _pool


class CacheClient:
    """Thin wrapper com serialização JSON e tratamento de falhas silencioso."""

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = get_redis()
        return self._client

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self.client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("cache_get_error", extra={"key": key, "error": str(exc)})
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        try:
            serialized = json.dumps(value, default=str)
            await self.client.setex(key, ttl, serialized)
            return True
        except Exception as exc:
            logger.warning("cache_set_error", extra={"key": key, "error": str(exc)})
            return False

    async def delete(self, key: str) -> bool:
        try:
            await self.client.delete(key)
            return True
        except Exception as exc:
            logger.warning("cache_delete_error", extra={"key": key, "error": str(exc)})
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Remove todas as chaves que combinam com o padrão (SCAN, não KEYS)."""
        try:
            deleted = 0
            async for key in self.client.scan_iter(pattern, count=100):
                await self.client.delete(key)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.warning(
                "cache_delete_pattern_error",
                extra={"pattern": pattern, "error": str(exc)},
            )
            return 0

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception:
            return False


cache = CacheClient()

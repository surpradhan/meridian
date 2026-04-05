"""
Query Result Caching with Redis

Provides caching layer for query results with configurable TTL,
cache invalidation strategies, and cache statistics.
"""

import json
import hashlib
import logging
from typing import Any, Optional, Dict, List
from datetime import timedelta

try:
    import redis
    from redis import Redis
except ImportError:
    redis = None

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

    def retry(*args, **kwargs):  # type: ignore[misc]
        def decorator(func):
            return func
        return decorator

    def stop_after_attempt(n):  # type: ignore[misc]
        return None

    def wait_exponential(**kwargs):  # type: ignore[misc]
        return None

    def retry_if_exception_type(exc):  # type: ignore[misc]
        return None

logger = logging.getLogger(__name__)


class CacheConfig:
    """Configuration for caching."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        ttl_seconds: int = 3600,
        enabled: bool = True,
        key_prefix: str = "meridian:",
    ):
        self.host = host
        self.port = port
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self.key_prefix = key_prefix


class CacheManager:
    """Manages query result caching with Redis."""

    _instance: Optional["CacheManager"] = None

    def __init__(self, config: CacheConfig):
        self.config = config
        self.client: Optional[Redis] = None
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }

        if config.enabled and redis:
            self._connect()

    def _connect(self) -> None:
        """Connect to Redis."""
        try:
            self.client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            self.client.ping()
            logger.info(
                f"Connected to Redis at {self.config.host}:{self.config.port}"
            )
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self.client = None

    @classmethod
    def get_instance(
        cls, config: Optional[CacheConfig] = None
    ) -> "CacheManager":
        """Get or create singleton instance."""
        if cls._instance is None:
            cfg = config or CacheConfig()
            cls._instance = cls(cfg)
        return cls._instance

    def _make_key(self, query: str, params: Optional[Dict] = None) -> str:
        """Generate cache key from query and parameters.

        Uses hash of query + params to create a deterministic key.
        """
        if params:
            key_data = f"{query}:{json.dumps(params, sort_keys=True)}"
        else:
            key_data = query

        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{self.config.key_prefix}query:{key_hash}"

    def get(self, query: str, params: Optional[Dict] = None) -> Optional[List[Dict]]:
        """Get cached query result.

        Args:
            query: SQL query or question string
            params: Query parameters/filters

        Returns:
            Cached result or None if not found
        """
        if not self.client:
            self.stats["misses"] += 1
            return None

        try:
            key = self._make_key(query, params)
            cached = self.client.get(key)

            if cached:
                self.stats["hits"] += 1
                result = json.loads(cached)
                logger.debug(f"Cache hit for key: {key}")
                return result
            else:
                self.stats["misses"] += 1
                return None

        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            self.stats["misses"] += 1
            return None

    def set(
        self,
        query: str,
        result: List[Dict],
        params: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """Cache query result.

        Args:
            query: SQL query or question string
            result: Query result rows
            params: Query parameters
            ttl_seconds: Time-to-live in seconds (uses config default if None)

        Returns:
            True if successfully cached
        """
        if not self.client:
            return False

        try:
            key = self._make_key(query, params)
            ttl = ttl_seconds or self.config.ttl_seconds

            self.client.setex(
                key,
                ttl,
                json.dumps(result),
            )
            self.stats["sets"] += 1
            logger.debug(f"Cached result for key: {key} (TTL: {ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Cache set failed: {e}")
            return False

    def get_result(self, query: str) -> Optional[Dict]:
        """Get a single cached orchestrator result dict.

        Args:
            query: Natural language query string

        Returns:
            Cached result dict or None if not found
        """
        if not self.client:
            self.stats["misses"] += 1
            return None

        try:
            key = self._make_key(f"result:{query}")
            cached = self.client.get(key)
            if cached:
                self.stats["hits"] += 1
                logger.debug(f"Cache hit for result key: {key}")
                return json.loads(cached)
            self.stats["misses"] += 1
            return None
        except Exception as e:
            logger.error(f"Cache get_result failed: {e}")
            self.stats["misses"] += 1
            return None

    def set_result(self, query: str, result: Dict, ttl_seconds: Optional[int] = None) -> bool:
        """Cache a single orchestrator result dict.

        Args:
            query: Natural language query string
            result: Orchestrator result dict
            ttl_seconds: Time-to-live in seconds (uses config default if None)

        Returns:
            True if successfully cached
        """
        if not self.client:
            return False

        try:
            key = self._make_key(f"result:{query}")
            ttl = ttl_seconds or self.config.ttl_seconds
            self.client.setex(key, ttl, json.dumps(result))
            self.stats["sets"] += 1
            logger.debug(f"Cached result for key: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache set_result failed: {e}")
            return False

    def invalidate(self, pattern: str = "*") -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "meridian:query:*")

        Returns:
            Number of keys deleted
        """
        if not self.client:
            return 0

        try:
            full_pattern = f"{self.config.key_prefix}{pattern}"
            keys = self.client.keys(full_pattern)
            if keys:
                deleted = self.client.delete(*keys)
                self.stats["deletes"] += deleted
                logger.info(f"Invalidated {deleted} cache entries")
                return deleted
            return 0

        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            return 0

    def invalidate_query(self, query: str, params: Optional[Dict] = None) -> bool:
        """Invalidate specific query result.

        Args:
            query: SQL query or question string
            params: Query parameters

        Returns:
            True if invalidated
        """
        if not self.client:
            return False

        try:
            key = self._make_key(query, params)
            deleted = self.client.delete(key)
            if deleted:
                self.stats["deletes"] += 1
            return bool(deleted)

        except Exception as e:
            logger.error(f"Query invalidation failed: {e}")
            return False

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        if not self.client:
            return 0

        try:
            pattern = f"{self.config.key_prefix}*"
            keys = self.client.keys(pattern)
            if keys:
                deleted = self.client.delete(*keys)
                self.stats["deletes"] += deleted
                logger.info(f"Cleared {deleted} cache entries")
                return deleted
            return 0

        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache hit/miss/set/delete counts and hit rate
        """
        total_reads = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            self.stats["hits"] / total_reads if total_reads > 0 else 0.0
        )

        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "sets": self.stats["sets"],
            "deletes": self.stats["deletes"],
            "hit_rate": hit_rate,
            "total_reads": total_reads,
            "connected": self.client is not None,
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }


def setup_cache(
    host: str = "localhost",
    port: int = 6379,
    ttl_seconds: int = 3600,
    enabled: bool = True,
) -> CacheManager:
    """Setup caching globally.

    Args:
        host: Redis host
        port: Redis port
        ttl_seconds: Default TTL for cached entries
        enabled: Whether to enable caching

    Returns:
        CacheManager instance
    """
    config = CacheConfig(
        host=host,
        port=port,
        ttl_seconds=ttl_seconds,
        enabled=enabled,
    )
    return CacheManager.get_instance(config)


def get_cache() -> CacheManager:
    """Get global cache instance."""
    return CacheManager.get_instance()

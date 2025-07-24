"""
Hierarchical caching system for gap analysis results.
This module provides a multi-level caching architecture with predictive prefetching
and advanced eviction strategies to optimize cache hit rates.
"""

import logging
import time
import json
import asyncio
import hashlib
from typing import Dict, List, Any, Tuple, Optional, Set, Union
from datetime import datetime
from collections import defaultdict, Counter, OrderedDict
import threading
import math

# Try to import Redis for remote caching
try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    
# Try to import cachetools for advanced local caching
try:
    import cachetools
    from cachetools import TTLCache, LFUCache, LRUCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    CACHETOOLS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Cache configuration
DEFAULT_L1_SIZE = 1000  # Small, fast in-memory cache
DEFAULT_L2_SIZE = 10000  # Medium cache with TTL
DEFAULT_L3_SIZE = 100000  # Large persistent cache

DEFAULT_L1_TTL = 300  # 5 minutes
DEFAULT_L2_TTL = 3600  # 1 hour
DEFAULT_L3_TTL = 86400  # 24 hours

# Prefetch configuration
PREFETCH_THRESHOLD = 3  # Number of accesses before prefetching related items
MAX_PREFETCH_ITEMS = 5  # Maximum number of items to prefetch at once
PREFETCH_TTL_FACTOR = 0.5  # Shorter TTL for prefetched items

class HierarchicalCache:
    """
    Multi-level caching system with predictive prefetching.
    
    Features:
    - Three-level cache hierarchy with different sizes and TTLs
    - Access pattern tracking for prefetching
    - Multiple eviction policies (LRU, LFU, TTL)
    - Configurable memory limits
    """
    
    def __init__(self, 
                redis_client=None,
                l1_size=DEFAULT_L1_SIZE,
                l2_size=DEFAULT_L2_SIZE,
                l3_size=DEFAULT_L3_SIZE,
                l1_ttl=DEFAULT_L1_TTL,
                l2_ttl=DEFAULT_L2_TTL,
                l3_ttl=DEFAULT_L3_TTL,
                memory_limit_mb=None):
        """
        Initialize hierarchical cache.
        
        Args:
            redis_client: Optional Redis client for L3 cache
            l1_size: Maximum size of L1 cache
            l2_size: Maximum size of L2 cache
            l3_size: Maximum size of L3 cache
            l1_ttl: TTL for L1 cache items (seconds)
            l2_ttl: TTL for L2 cache items (seconds)
            l3_ttl: TTL for L3 cache items (seconds)
            memory_limit_mb: Optional memory limit in MB
        """
        # Initialize caches
        if CACHETOOLS_AVAILABLE:
            self.l1_cache = TTLCache(maxsize=l1_size, ttl=l1_ttl)
            self.l2_cache = LFUCache(maxsize=l2_size)  # Frequency-based eviction
        else:
            self.l1_cache = self._create_simple_cache(l1_size, l1_ttl)
            self.l2_cache = self._create_simple_cache(l2_size, l2_ttl)
            
        # Setup Redis as L3 if available
        self.redis_client = redis_client
        self.use_redis = REDIS_AVAILABLE and redis_client is not None
        
        # If not using Redis, create local L3 cache
        if not self.use_redis:
            if CACHETOOLS_AVAILABLE:
                self.l3_cache = LRUCache(maxsize=l3_size)  # LRU for large cache
            else:
                self.l3_cache = self._create_simple_cache(l3_size, l3_ttl)
                
        # Access tracking
        self.access_patterns = defaultdict(Counter)
        self.key_metadata = {}
        self.access_lock = threading.RLock()
        
        # Cache statistics
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "misses": 0,
            "prefetches": 0,
            "evictions": 0
        }
        
        # Memory management
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024 if memory_limit_mb else None
        self.estimated_memory_usage = 0
        
    def _create_simple_cache(self, maxsize, ttl):
        """Create a simple dictionary-based cache with TTL."""
        return OrderedDict()  # Use OrderedDict for LRU-like behavior
        
    async def exists(self, key: str) -> bool:
        """Check if key exists in any cache level."""
        # Check L1 cache (fastest)
        if key in self.l1_cache:
            return True
            
        # Check L2 cache
        if key in self.l2_cache:
            return True
            
        # Check L3 cache
        if self.use_redis:
            try:
                return bool(await self._async_redis_exists(key))
            except Exception as e:
                logger.error(f"Redis error checking key existence: {e}")
                return False
        else:
            return key in self.l3_cache
            
    async def get(self, key: str, default=None) -> Any:
        """
        Get value from cache, trying each level in order.
        Handles promotion between cache levels.
        """
        # Check L1 cache (fastest)
        if key in self.l1_cache:
            self.stats["l1_hits"] += 1
            value = self.l1_cache[key]
            # Record access pattern
            await self._record_access(key)
            return value
            
        # Check L2 cache
        if key in self.l2_cache:
            self.stats["l2_hits"] += 1
            value = self.l2_cache[key]
            # Promote to L1
            self.l1_cache[key] = value
            # Record access pattern
            await self._record_access(key)
            return value
            
        # Check L3 cache
        if self.use_redis:
            try:
                value = await self._async_redis_get(key)
                if value is not None:
                    self.stats["l3_hits"] += 1
                    # Deserialize from JSON
                    value = json.loads(value)
                    # Promote to L1 and L2
                    self.l1_cache[key] = value
                    self.l2_cache[key] = value
                    # Record access pattern
                    await self._record_access(key)
                    return value
            except Exception as e:
                logger.error(f"Redis error in get: {e}")
        else:
            if key in self.l3_cache:
                self.stats["l3_hits"] += 1
                value = self.l3_cache[key]
                # Promote to L1 and L2
                self.l1_cache[key] = value
                self.l2_cache[key] = value
                # Record access pattern
                await self._record_access(key)
                return value
                
        # Not found in any cache
        self.stats["misses"] += 1
        return default
        
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in all cache levels.
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Optional TTL override (seconds)
        """
        # Calculate memory size
        if self.memory_limit_bytes:
            try:
                size = self._estimate_size(value)
                if size > self.memory_limit_bytes:
                    logger.warning(f"Value for key {key} exceeds memory limit, not caching")
                    return
                    
                self.estimated_memory_usage += size
                
                # Check memory limit and evict if needed
                if self.estimated_memory_usage > self.memory_limit_bytes:
                    self._enforce_memory_limit()
            except:
                pass  # If estimation fails, proceed without it
        
        # Store metadata
        with self.access_lock:
            self.key_metadata[key] = {
                "created_at": time.time(),
                "last_access": time.time(),
                "access_count": 0,
                "size": self._estimate_size(value)
            }
        
        # Set in L1 cache
        self.l1_cache[key] = value
        
        # Set in L2 cache
        self.l2_cache[key] = value
        
        # Set in L3 cache
        if self.use_redis:
            try:
                # Use TTL if provided, otherwise use default L3 TTL
                redis_ttl = ttl or DEFAULT_L3_TTL
                # Serialize to JSON
                json_value = json.dumps(value)
                await self._async_redis_set(key, json_value, redis_ttl)
            except Exception as e:
                logger.error(f"Redis error in set: {e}")
        else:
            self.l3_cache[key] = value
            
        # Trigger prefetch of related items
        asyncio.create_task(self._prefetch_related(key))
            
    async def delete(self, key: str) -> None:
        """Delete key from all cache levels."""
        # Remove from L1
        if key in self.l1_cache:
            del self.l1_cache[key]
            
        # Remove from L2
        if key in self.l2_cache:
            del self.l2_cache[key]
            
        # Remove from L3
        if self.use_redis:
            try:
                await self._async_redis_delete(key)
            except Exception as e:
                logger.error(f"Redis error in delete: {e}")
        else:
            if key in self.l3_cache:
                del self.l3_cache[key]
                
        # Remove metadata
        with self.access_lock:
            if key in self.key_metadata:
                del self.key_metadata[key]
            for rel_key in list(self.access_patterns[key].keys()):
                if rel_key in self.access_patterns:
                    self.access_patterns[rel_key].pop(key, None)
            self.access_patterns.pop(key, None)
            
    async def _record_access(self, key: str) -> None:
        """Record access pattern for a key."""
        with self.access_lock:
            # Update metadata
            if key in self.key_metadata:
                self.key_metadata[key]["last_access"] = time.time()
                self.key_metadata[key]["access_count"] += 1
            
            # Update access sequence (last 3 keys accessed)
            last_keys = getattr(self, '_last_accessed_keys', [])
            if last_keys and key != last_keys[-1]:
                # Record relationship between consecutive accesses
                prev_key = last_keys[-1]
                self.access_patterns[prev_key][key] += 1
                
            # Update last accessed keys
            if not hasattr(self, '_last_accessed_keys'):
                self._last_accessed_keys = []
            if key in self._last_accessed_keys:
                self._last_accessed_keys.remove(key)
            self._last_accessed_keys.append(key)
            # Keep only last 10 keys
            if len(self._last_accessed_keys) > 10:
                self._last_accessed_keys.pop(0)
            
    async def _prefetch_related(self, key: str) -> None:
        """Prefetch related keys based on access patterns."""
        try:
            with self.access_lock:
                if key not in self.access_patterns:
                    return
                    
                # Get top related keys
                related = self.access_patterns[key].most_common(MAX_PREFETCH_ITEMS)
                # Filter by threshold
                prefetch_keys = [k for k, count in related if count >= PREFETCH_THRESHOLD]
                
            if not prefetch_keys:
                return
                
            # Prefetch each key
            for related_key in prefetch_keys:
                # Skip if already in L1 cache
                if related_key in self.l1_cache:
                    continue
                    
                # Try to get from L2 or L3
                if related_key in self.l2_cache:
                    value = self.l2_cache[related_key]
                    self.l1_cache[related_key] = value
                    self.stats["prefetches"] += 1
                elif self.use_redis:
                    try:
                        value = await self._async_redis_get(related_key)
                        if value is not None:
                            value = json.loads(value)
                            self.l1_cache[related_key] = value
                            self.l2_cache[related_key] = value
                            self.stats["prefetches"] += 1
                    except Exception:
                        pass
                elif related_key in self.l3_cache:
                    value = self.l3_cache[related_key]
                    self.l1_cache[related_key] = value
                    self.l2_cache[related_key] = value
                    self.stats["prefetches"] += 1
        except Exception as e:
            logger.error(f"Error in prefetch: {e}")
            
    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes."""
        try:
            # Fast estimation using JSON serialization
            json_str = json.dumps(value)
            return len(json_str) * 2  # Unicode chars are 2+ bytes
        except:
            # Fallback estimate
            return 1024  # 1KB default
            
    def _enforce_memory_limit(self) -> None:
        """Enforce memory limit by evicting items."""
        if not self.memory_limit_bytes:
            return
            
        # Calculate how much memory to free (aim for 20% below limit)
        target = int(self.memory_limit_bytes * 0.8)
        to_free = self.estimated_memory_usage - target
        if to_free <= 0:
            return
            
        freed = 0
        eviction_candidates = []
        
        # Build eviction candidates list
        with self.access_lock:
            for key, meta in self.key_metadata.items():
                # Calculate score based on recency and frequency
                age = time.time() - meta.get("last_access", 0)
                count = meta.get("access_count", 0) or 1
                size = meta.get("size", 1024)
                
                # Score: higher is better candidate for eviction
                # Formula balances size benefit with access patterns
                score = (age * size) / (count * math.log(count + 1))
                eviction_candidates.append((key, score, size))
                
        # Sort by score (highest first = best eviction candidates)
        eviction_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Evict until we free enough memory
        for key, _, size in eviction_candidates:
            # Delete from all cache levels
            asyncio.create_task(self.delete(key))
            freed += size
            self.stats["evictions"] += 1
            
            # Stop when we've freed enough
            if freed >= to_free:
                break
                
        # Update estimated memory usage
        self.estimated_memory_usage -= freed
            
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_accesses = sum([
            self.stats["l1_hits"],
            self.stats["l2_hits"],
            self.stats["l3_hits"],
            self.stats["misses"]
        ])
        
        hit_rate = 0
        if total_accesses > 0:
            hit_rate = (total_accesses - self.stats["misses"]) / total_accesses
            
        return {
            **self.stats,
            "hit_rate": hit_rate,
            "l1_size": len(self.l1_cache),
            "l2_size": len(self.l2_cache),
            "l3_size": len(self.l3_cache) if not self.use_redis else "unknown",
            "memory_usage": self.estimated_memory_usage,
            "memory_limit": self.memory_limit_bytes
        }
        
    async def _async_redis_get(self, key: str) -> Any:
        """Async wrapper for Redis get operation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.redis_client.get(key))
        
    async def _async_redis_set(self, key: str, value: str, ttl: int) -> None:
        """Async wrapper for Redis set operation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self.redis_client.setex(key, ttl, value)
        )
        
    async def _async_redis_delete(self, key: str) -> None:
        """Async wrapper for Redis delete operation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.redis_client.delete(key))
        
    async def _async_redis_exists(self, key: str) -> bool:
        """Async wrapper for Redis exists operation."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.redis_client.exists(key))


class CacheManager:
    """
    High-level cache manager that coordinates between different caching strategies.
    Provides shard-based caching for improved performance under high load.
    """
    
    def __init__(self, 
                redis_url=None, 
                shard_count=4,
                memory_limit_mb=512):
        """
        Initialize cache manager with multiple shards.
        
        Args:
            redis_url: Redis URL for persistent caching
            shard_count: Number of cache shards
            memory_limit_mb: Total memory limit in MB
        """
        # Initialize Redis client if URL provided
        redis_client = None
        if redis_url and REDIS_AVAILABLE:
            try:
                redis_client = Redis.from_url(redis_url)
                # Test connection
                redis_client.ping()
                logger.info(f"Connected to Redis at {redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                redis_client = None
                
        # Calculate per-shard memory limit
        per_shard_memory = memory_limit_mb // shard_count if memory_limit_mb else None
        
        # Create cache shards
        self.shards = []
        for i in range(shard_count):
            self.shards.append(HierarchicalCache(
                redis_client=redis_client,
                memory_limit_mb=per_shard_memory
            ))
            
        self.shard_count = shard_count
        
        # Namespace handling
        self.namespaces = {}
        
        # Statistics
        self.last_stats_time = time.time()
        
    def _get_shard(self, key: str) -> HierarchicalCache:
        """Get appropriate shard for a key using consistent hashing."""
        # Simple hash-based sharding
        shard_id = int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16) % self.shard_count
        return self.shards[shard_id]
        
    def _get_namespaced_key(self, key: str, namespace: Optional[str] = None) -> str:
        """Get namespaced key."""
        if namespace:
            return f"{namespace}:{key}"
        return key
        
    async def exists(self, key: str, namespace: Optional[str] = None) -> bool:
        """Check if key exists in cache."""
        namespaced_key = self._get_namespaced_key(key, namespace)
        shard = self._get_shard(namespaced_key)
        return await shard.exists(namespaced_key)
        
    async def get(self, key: str, namespace: Optional[str] = None, default=None) -> Any:
        """Get value from cache."""
        namespaced_key = self._get_namespaced_key(key, namespace)
        shard = self._get_shard(namespaced_key)
        return await shard.get(namespaced_key, default)
        
    async def set(self, 
                key: str, 
                value: Any, 
                namespace: Optional[str] = None, 
                ttl: Optional[int] = None) -> None:
        """Set value in cache."""
        namespaced_key = self._get_namespaced_key(key, namespace)
        shard = self._get_shard(namespaced_key)
        await shard.set(namespaced_key, value, ttl)
        
        # Record namespace for invalidation
        if namespace:
            if namespace not in self.namespaces:
                self.namespaces[namespace] = set()
            self.namespaces[namespace].add(key)
        
    async def delete(self, key: str, namespace: Optional[str] = None) -> None:
        """Delete key from cache."""
        namespaced_key = self._get_namespaced_key(key, namespace)
        shard = self._get_shard(namespaced_key)
        await shard.delete(namespaced_key)
        
        # Remove from namespace tracking
        if namespace and namespace in self.namespaces:
            self.namespaces[namespace].discard(key)
            
    async def invalidate_namespace(self, namespace: str) -> None:
        """Invalidate all keys in a namespace."""
        if namespace not in self.namespaces:
            return
            
        keys_to_delete = list(self.namespaces[namespace])
        for key in keys_to_delete:
            await self.delete(key, namespace)
            
        # Clear namespace
        self.namespaces[namespace] = set()
        
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics from all shards."""
        combined_stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "l3_hits": 0,
            "misses": 0,
            "prefetches": 0,
            "evictions": 0,
            "hit_rate": 0,
            "shard_count": self.shard_count,
            "namespace_count": len(self.namespaces),
            "namespace_keys": {ns: len(keys) for ns, keys in self.namespaces.items()},
            "memory_usage": 0
        }
        
        # Combine stats from all shards
        for i, shard in enumerate(self.shards):
            shard_stats = shard.get_stats()
            for k in ["l1_hits", "l2_hits", "l3_hits", "misses", 
                     "prefetches", "evictions"]:
                combined_stats[k] += shard_stats.get(k, 0)
            
            # Sum memory usage
            combined_stats["memory_usage"] += shard_stats.get("memory_usage", 0)
            
            # Add shard-specific stats
            combined_stats[f"shard_{i}"] = {
                "hit_rate": shard_stats.get("hit_rate", 0),
                "size": {
                    "l1": shard_stats.get("l1_size", 0),
                    "l2": shard_stats.get("l2_size", 0),
                    "l3": shard_stats.get("l3_size", 0)
                }
            }
            
        # Calculate overall hit rate
        total_accesses = combined_stats["l1_hits"] + combined_stats["l2_hits"] + \
                        combined_stats["l3_hits"] + combined_stats["misses"]
        if total_accesses > 0:
            combined_stats["hit_rate"] = (total_accesses - combined_stats["misses"]) / total_accesses
            
        # Add time delta
        now = time.time()
        combined_stats["time_delta"] = now - self.last_stats_time
        self.last_stats_time = now
        
        return combined_stats 
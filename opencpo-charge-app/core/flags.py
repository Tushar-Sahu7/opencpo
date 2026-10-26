"""Feature flag reader — fetches from Core API with 60-second in-memory cache."""
import logging
import time

from core.api import api_get

logger = logging.getLogger(__name__)

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL: int = 10  # seconds


async def get_flags() -> dict:
    """Return feature flags dict. Cached for 10s. Returns {} on error."""
    global _cache, _cache_ts
    now = time.monotonic()
    if now - _cache_ts < _CACHE_TTL and _cache is not None:
        return _cache
    try:
        data = await api_get("/api/v1/features")
        if isinstance(data, dict):
            # API returns {"flags": {...}, "details": [...]} — extract the flags sub-dict
            flags_data = data.get("flags", data)
            _cache = flags_data
            _cache_ts = now
            return _cache
    except Exception as e:
        logger.warning(f"Could not fetch feature flags: {e}")
    return {}

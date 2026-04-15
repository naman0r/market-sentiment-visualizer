"""
File-based caching module for market sentiment data.

Market data changes frequently during trading hours but is static overnight
and on weekends. This cache respects market hours so we don't hammer data
sources when prices aren't moving anyway.
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
EASTERN = ZoneInfo("America/New_York")

# Market session boundaries (Eastern Time)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# TTL in seconds for when markets are closed — no point refreshing stale data
EXTENDED_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _ensure_cache_dir() -> None:
    """Create the cache directory if it doesn't already exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(key: str) -> str:
    """Return the filesystem path for a given cache key.

    Keys are sanitized so they're safe as filenames (slashes become underscores).
    """
    safe_key = key.replace("/", "_").replace(" ", "_")
    return os.path.join(CACHE_DIR, f"{safe_key}.json")


def _is_market_open() -> bool:
    """Check whether the US equity market is currently open.

    The NYSE/NASDAQ are open Monday–Friday, 9:30 AM–4:00 PM Eastern Time.
    This does NOT account for market holidays — for caching purposes, the
    extended TTL on holidays is acceptable (the data just stays fresh longer).
    """
    now_et = datetime.now(EASTERN)

    # Weekends: Saturday = 5, Sunday = 6
    if now_et.weekday() >= 5:
        return False

    # Before market open
    if (now_et.hour, now_et.minute) < (MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE):
        return False

    # After market close
    if (now_et.hour, now_et.minute) >= (MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE):
        return False

    return True


def _effective_ttl(ttl: int) -> int:
    """Return the effective TTL for a cache entry.

    When markets are closed, data doesn't change, so we extend the TTL to
    24 hours to avoid unnecessary network calls overnight or on weekends.
    """
    if not _is_market_open():
        return max(ttl, EXTENDED_TTL_SECONDS)
    return ttl


def get(key: str) -> dict | None:
    """Retrieve cached data for *key* if it exists and is still fresh.

    Returns the cached payload dict if the entry exists and hasn't expired,
    or None if the cache is missing, expired, or unreadable.

    Args:
        key: Logical cache key, e.g. ``"vix"`` or ``"sectors"``.

    Returns:
        The previously cached data dict, or ``None`` on a cache miss.
    """
    _ensure_cache_dir()
    path = _cache_path(key)

    if not os.path.exists(path):
        logger.debug("Cache miss (no file): %s", key)
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            envelope = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cache file unreadable for key %s: %s", key, exc)
        return None

    stored_at: float = envelope.get("stored_at", 0.0)
    ttl: int = envelope.get("ttl", 900)
    effective = _effective_ttl(ttl)

    age = time.time() - stored_at
    if age > effective:
        logger.debug("Cache expired for key %s (age=%.0fs, ttl=%ds)", key, age, effective)
        return None

    logger.debug("Cache hit for key %s (age=%.0fs)", key, age)
    return envelope.get("data")


def set(key: str, data: dict, ttl: int = 900) -> None:  # noqa: A001
    """Persist *data* to the file cache under *key*.

    The entry is written atomically-ish by writing to a temp file and then
    renaming, which avoids partially-written JSON being read back.

    Args:
        key: Logical cache key.
        data: Arbitrary JSON-serialisable dict to store.
        ttl:  Time-to-live in seconds (default 900 = 15 minutes). The actual
              TTL may be extended if markets are closed.
    """
    _ensure_cache_dir()
    path = _cache_path(key)
    tmp_path = path + ".tmp"

    envelope = {
        "stored_at": time.time(),
        "ttl": ttl,
        "data": data,
    }

    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh, default=str)
        os.replace(tmp_path, path)
        logger.debug("Cache set for key %s (ttl=%ds)", key, ttl)
    except OSError as exc:
        logger.error("Failed to write cache for key %s: %s", key, exc)
        # Non-fatal — we just won't cache this response
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def get_stale(key: str) -> dict | None:
    """Return cached data regardless of expiry, used as a last-resort fallback.

    When live data fetching fails we'd rather show slightly stale data than
    crash the endpoint. This reads the cache file without checking the TTL.

    Args:
        key: Logical cache key.

    Returns:
        The cached data dict if any file exists, otherwise ``None``.
    """
    _ensure_cache_dir()
    path = _cache_path(key)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            envelope = json.load(fh)
        logger.info("Serving stale cache for key %s", key)
        return envelope.get("data")
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Stale cache unreadable for key %s: %s", key, exc)
        return None


def invalidate(key: str) -> None:
    """Delete the cache file for *key*, forcing a fresh fetch next time.

    Args:
        key: Logical cache key to evict.
    """
    path = _cache_path(key)
    try:
        os.remove(path)
        logger.debug("Cache invalidated for key %s", key)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not invalidate cache key %s: %s", key, exc)

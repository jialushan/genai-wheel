"""
Simple JSON-backed score cache with a 24-hour TTL.

Cached entries are keyed by tool name (case-insensitive). Each entry stores
the score and the unix timestamp when it was computed.
"""

import json
import os
import time

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", ".score_cache.json")
TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _load():
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _key(name):
    return name.strip().lower()


def get(name):
    """Return cached score if fresh, else None."""
    cache = _load()
    entry = cache.get(_key(name))
    if not entry:
        return None
    if time.time() - entry.get("timestamp", 0) > TTL_SECONDS:
        return None
    return entry.get("score")


def set_score(name, score):
    """Store a score for a tool with the current timestamp."""
    cache = _load()
    cache[_key(name)] = {"score": score, "timestamp": time.time()}
    _save(cache)


def clear():
    """Wipe the cache (useful for testing)."""
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)

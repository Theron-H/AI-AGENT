from __future__ import annotations

import json
import os
from typing import Any

from redis import Redis


def get_redis() -> Redis | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    return Redis.from_url(url, decode_responses=True)


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, json.dumps(value))
    except Exception:
        return

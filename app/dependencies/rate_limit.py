"""Lightweight in-memory sliding-window rate limiter.

Adequate for a single-process MVP. Swap the ``_buckets`` store for Redis when
scaling to multiple workers (see security.md §7).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitError

_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(rule_name: str):
    """Dependency factory. ``rule_name`` maps to a ``RATE_LIMIT_<NAME>`` setting."""

    async def _limiter(request: Request) -> None:
        rule = settings.rate_rule(rule_name)
        client = request.client.host if request.client else "unknown"
        key = f"{rule_name}:{client}"
        now = time.monotonic()
        bucket = _buckets[key]
        while bucket and now - bucket[0] > rule.window:
            bucket.popleft()
        if len(bucket) >= rule.limit:
            raise RateLimitError()
        bucket.append(now)

    return _limiter

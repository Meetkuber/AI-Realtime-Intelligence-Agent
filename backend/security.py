"""
security.py — Rate Limiting + Prompt Injection Defense
============================================================
1. Per-IP rate limiting using a simple sliding-window approach
   (avoids slowapi dependency for Python 3.14 compatibility)
2. Prompt injection detection — rejects inputs that attempt to
   override the system prompt or inject instructions
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Sliding-window rate limiter
# ─────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Simple in-process sliding-window rate limiter.
    For production: use Redis-backed sliding window.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window
        bucket = self._buckets[key]

        # Evict old timestamps
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return False

        bucket.append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        window_start = now - self.window
        bucket = self._buckets[key]
        active = sum(1 for ts in bucket if ts >= window_start)
        return max(0, self.max_requests - active)


# Limits: 10 voice calls/min, 30 text/min per IP
voice_limiter = RateLimiter(max_requests=10, window_seconds=60)
text_limiter  = RateLimiter(max_requests=30, window_seconds=60)


def check_rate_limit(request: Request, limiter: RateLimiter, endpoint: str) -> None:
    """Raise HTTP 429 if the IP has exceeded the rate limit."""
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.is_allowed(client_ip):
        logger.warning(f"[RateLimit] {client_ip} exceeded limit on {endpoint}")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {limiter.max_requests} requests per {limiter.window}s.",
            headers={"Retry-After": str(limiter.window)},
        )


# ─────────────────────────────────────────────────────────────
# Prompt Injection Defense
# ─────────────────────────────────────────────────────────────

# Patterns that indicate attempts to override the system prompt
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your instructions",
    "you are now",
    "new instructions:",
    "system prompt:",
    "forget your previous",
    "act as",
    "pretend you are",
    "roleplay as",
    "your new persona",
    "override system",
    "jailbreak",
    "dan mode",
    "developer mode",
    "ignore the above",
    "\\n\\nsystem:",
    "\\nsystem:",
    "[system]",
    "<|system|>",
    "<!-- system",
]


def check_prompt_injection(text: str) -> None:
    """
    Raise HTTP 400 if the text contains prompt injection patterns.
    Logs the attempt for security monitoring.
    """
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in text_lower:
            logger.warning(
                f"[Security] Prompt injection attempt detected. "
                f"Pattern: {pattern!r} | Input snippet: {text[:100]!r}"
            )
            raise HTTPException(
                status_code=400,
                detail="Input contains disallowed content. Please rephrase your request.",
            )


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Trim input and strip null bytes."""
    return text.replace("\x00", "").strip()[:max_length]

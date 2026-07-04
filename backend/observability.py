"""
observability.py — Structured Logging + In-Memory Metrics
============================================================
Every request gets a trace_id. Metrics are stored in-memory
(and also persisted to SQLite via database.py) and exposed
at GET /api/metrics for dashboard consumption.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

# ─────────────────────────────────────────────────────────────
# Structured JSON Logger
# ─────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines — grep/jq friendly."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            payload["trace_id"] = record.trace_id
        if hasattr(record, "tool"):
            payload["tool"] = record.tool
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        import json as _json
        return _json.dumps(payload)


def configure_logging(json_mode: bool = False) -> None:
    """Call once at startup to configure root logger."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    if json_mode:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s", "%H:%M:%S"
        ))

    root.handlers.clear()
    root.addHandler(handler)


def get_trace_id() -> str:
    return str(uuid.uuid4())[:8]


# ─────────────────────────────────────────────────────────────
# In-Memory Metrics Store
# ─────────────────────────────────────────────────────────────

class MetricsStore:
    """
    Thread-safe in-memory metrics collector.
    Keeps a rolling window of the last 1000 requests.
    """

    def __init__(self, window: int = 1000):
        self._window = window
        self._latencies: deque[float] = deque(maxlen=window)  # all request durations
        self._tool_counts: dict[str, int] = defaultdict(int)
        self._error_count: int = 0
        self._request_count: int = 0
        self._tool_latencies: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._started_at = datetime.utcnow().isoformat() + "Z"

    def record_request(self, duration_ms: float, success: bool) -> None:
        self._request_count += 1
        self._latencies.append(duration_ms)
        if not success:
            self._error_count += 1

    def record_tool(self, tool_name: str, duration_ms: float | None = None) -> None:
        self._tool_counts[tool_name] += 1
        if duration_ms is not None:
            self._tool_latencies[tool_name].append(duration_ms)

    def _percentile(self, data: list[float], p: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = int(len(s) * p / 100)
        return round(s[min(idx, len(s) - 1)], 1)

    def snapshot(self) -> dict[str, Any]:
        lats = list(self._latencies)
        return {
            "uptime_since": self._started_at,
            "requests_total": self._request_count,
            "errors_total": self._error_count,
            "error_rate_pct": round(self._error_count / max(self._request_count, 1) * 100, 2),
            "latency": {
                "p50_ms": self._percentile(lats, 50),
                "p75_ms": self._percentile(lats, 75),
                "p95_ms": self._percentile(lats, 95),
                "p99_ms": self._percentile(lats, 99),
                "avg_ms": round(sum(lats) / len(lats), 1) if lats else 0,
            },
            "tool_calls": {
                name: {
                    "count": count,
                    "avg_ms": round(
                        sum(self._tool_latencies[name]) / len(self._tool_latencies[name]), 1
                    ) if self._tool_latencies[name] else None,
                }
                for name, count in self._tool_counts.items()
            },
        }


# Global singleton
metrics = MetricsStore()

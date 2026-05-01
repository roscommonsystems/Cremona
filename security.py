"""
security.py — Per-request security guards for the Quart app.

Provides:
  - get_client_ip_ws()     Real client IP from a WebSocket context
  - check_ws_rate_limit()  Sliding-window rate limiter for WS upgrades (per IP)
  - track_session()        Context manager that enforces concurrent session limits
  - RateLimitExceeded      Raised when the rate limit is hit
  - TooManySessions        Raised when concurrent session limits are hit

NOTE: All state is in-process. Limits are per-instance, not global across
Cloud Run instances. Use --max-instances in cloudbuild.yaml to cap total load.
"""

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from quart import websocket

from globals import (
    MAX_CONCURRENT_SESSIONS,
    MAX_SESSIONS_PER_IP,
    WS_RATE_LIMIT_COUNT,
    WS_RATE_LIMIT_WINDOW,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RateLimitExceeded(Exception):
    """Raised when an IP exceeds the WebSocket connection rate limit."""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Try again in {retry_after}s.")


class TooManySessions(Exception):
    """Raised when the global or per-IP concurrent session limit is hit."""
    pass


# ---------------------------------------------------------------------------
# IP extraction
# ---------------------------------------------------------------------------

async def get_client_ip_ws() -> str:
    """Return the real client IP from a WebSocket context.

    Uses access_route[0], which resolves X-Forwarded-For[0] when the header
    is present (e.g. behind Cloud Run's load balancer), and falls back to the
    direct connection address otherwise.

    IMPORTANT: Only trust X-Forwarded-For when the app is behind a known proxy
    (Cloud Run, nginx, etc.). Direct exposure without a proxy would allow
    clients to spoof their IP via the X-Forwarded-For header.
    """
    return websocket.access_route[0]


# ---------------------------------------------------------------------------
# WebSocket connection rate limiter (sliding window, per IP)
# ---------------------------------------------------------------------------

# Tracks recent connection timestamps per IP: {ip: [monotonic_timestamp, ...]}
# asyncio.Lock makes the dict mutations safe across concurrent coroutines.
_ws_rate_lock = asyncio.Lock()
_ws_connect_timestamps: dict[str, list[float]] = defaultdict(list)


async def check_ws_rate_limit(ip: str) -> None:
    """Enforce a sliding-window rate limit on WebSocket connection attempts.

    Raises RateLimitExceeded if the IP has made WS_RATE_LIMIT_COUNT or more
    connection attempts within the last WS_RATE_LIMIT_WINDOW seconds.

    Uses time.monotonic() (not wall clock) so it's immune to system clock
    adjustments or NTP corrections.
    """
    now = time.monotonic()
    async with _ws_rate_lock:
        # Evict timestamps that have fallen outside the current window
        cutoff = now - WS_RATE_LIMIT_WINDOW
        _ws_connect_timestamps[ip] = [t for t in _ws_connect_timestamps[ip] if t > cutoff]

        if len(_ws_connect_timestamps[ip]) >= WS_RATE_LIMIT_COUNT:
            # Calculate how many seconds until the oldest timestamp expires
            retry_after = int(_ws_connect_timestamps[ip][0] + WS_RATE_LIMIT_WINDOW - now) + 1
            raise RateLimitExceeded(retry_after)

        # Record this connection attempt
        _ws_connect_timestamps[ip].append(now)


# ---------------------------------------------------------------------------
# Concurrent session tracker
# ---------------------------------------------------------------------------

# Module-level counters mutated under _sessions_lock.
# In-process only — see module docstring about multi-instance behaviour.
_sessions_lock = asyncio.Lock()
_active_session_count = 0                                    # global count across all IPs
_active_sessions_by_ip: dict[str, int] = defaultdict(int)   # per-IP count


@asynccontextmanager
async def track_session(ip: str):
    """Context manager that acquires a session slot on entry and releases it on exit.

    Raises TooManySessions before acquiring if either:
      - the global cap (MAX_CONCURRENT_SESSIONS) is reached, or
      - the per-IP cap (MAX_SESSIONS_PER_IP) is reached.

    The finally block guarantees the slot is always released — even if the
    session errors, is cancelled, or times out. This prevents leaked counts.

    Usage:
        async with track_session(ip):
            # ... run the WebSocket session ...
    """
    global _active_session_count

    # Atomically check limits and acquire the slot
    async with _sessions_lock:
        if _active_session_count >= MAX_CONCURRENT_SESSIONS:
            raise TooManySessions("Server is at capacity. Please try again later.")
        if _active_sessions_by_ip[ip] >= MAX_SESSIONS_PER_IP:
            raise TooManySessions("Too many connections from your IP. Please close another session first.")
        _active_session_count += 1
        _active_sessions_by_ip[ip] += 1

    try:
        yield
    finally:
        # Always release the slot, regardless of how the session ended
        async with _sessions_lock:
            _active_session_count -= 1
            _active_sessions_by_ip[ip] -= 1
            # Remove the IP entry when it reaches zero to prevent unbounded dict growth
            if _active_sessions_by_ip[ip] <= 0:
                del _active_sessions_by_ip[ip]

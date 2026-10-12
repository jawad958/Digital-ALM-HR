"""Security middleware — headers + per-IP rate limiting.

Headers set on every response:
  - Strict-Transport-Security  (HTTPS enforcement in prod)
  - X-Content-Type-Options     (prevent MIME sniffing)
  - X-Frame-Options            (prevent clickjacking)
  - Referrer-Policy            (don't leak referrer)
  - Permissions-Policy         (disable camera/mic/geolocation by default)
  - Content-Security-Policy    (restricts script/style sources)

Rate limiter is a lightweight in-memory sliding window — enough for a solo-dev MVP.
Production should swap for a Redis-backed limiter (e.g. slowapi+redis).

Two things worth knowing about the limiter:

1. It is OFF in local/test by default. A dev SPA fans out several requests per
   page load, and React StrictMode double-invokes effects, so any limit tuned
   for real traffic trips constantly while developing. Override by setting
   RATE_LIMIT_ENABLED=true in .env.

2. It RETURNS a JSONResponse rather than raising HTTPException. Starlette
   installs its exception handlers *inside* the routing layer, which sits below
   custom BaseHTTPMiddleware — so an HTTPException raised here is never
   converted and surfaces to the client as a 500 instead of a 429.
"""

from collections import defaultdict, deque
from time import monotonic
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from alpago.core.config import settings
from alpago.core.logging import log


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers.setdefault("Content-Security-Policy", CSP)
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# ─────────── Rate limiter ────────────────────────────────────────────────

class _SlidingWindowLimiter:
    def __init__(self, max_keys: int = 10_000):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.max_keys = max_keys

    def check(self, key: str, limit: int, window_sec: float) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = monotonic()
        dq = self.hits[key]
        cutoff = now - window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= limit:
            retry_after = max(1, int(window_sec - (now - dq[0])) + 1)
            return False, retry_after

        dq.append(now)

        # Opportunistic pruning so an unbounded set of IPs can't grow the dict forever
        if len(self.hits) > self.max_keys:
            empty = [k for k, v in self.hits.items() if not v][: self.max_keys // 10]
            for k in empty:
                del self.hits[k]

        return True, 0


_limiter = _SlidingWindowLimiter()


# Per-path limits as (requests, window_seconds). The LONGEST matching prefix wins,
# so the tight login limit beats the generous one covering the rest of /auth.
RATE_LIMITS: dict[str, tuple[int, int]] = {
    # Brute-force protection — the ones that actually matter
    "/api/v1/auth/login": (10, 60),
    "/api/v1/auth/register": (5, 300),
    # Public candidate magic link
    "/api/v1/offers/public": (20, 60),
    # Authenticated reads — generous; one page load can fire 4-6 of these
    "/api/v1/auth": (300, 60),
    "/api/v1/approvals": (300, 60),
    "/api/v1/hiring": (300, 60),
    "/api/v1/candidates": (300, 60),
    "/api/v1/interviews": (300, 60),
    "/api/v1/offers": (300, 60),
    "/api/v1/employees": (300, 60),
    "/api/v1/documents": (300, 60),
    "/api/v1/activity": (300, 60),
}


def _rate_limiting_on() -> bool:
    """Off in local/test unless explicitly enabled via RATE_LIMIT_ENABLED."""
    explicit = getattr(settings, "rate_limit_enabled", None)
    if explicit is not None:
        return bool(explicit)
    return settings.env not in ("local", "test")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match_limit(path: str) -> tuple[str, int, int] | None:
    """Longest-prefix match against RATE_LIMITS."""
    best: tuple[str, int, int] | None = None
    for prefix, (limit, window) in RATE_LIMITS.items():
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, limit, window)
    return best


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        if not _rate_limiting_on():
            return await call_next(request)

        # Never rate-limit preflight — the browser controls that timing, not the user
        if request.method == "OPTIONS":
            return await call_next(request)

        matched = _match_limit(request.url.path)
        if matched is not None:
            prefix, limit, window = matched
            key = f"{_client_ip(request)}:{prefix}"
            allowed, retry_after = _limiter.check(key, limit, window)
            if not allowed:
                log.warning(
                    "ratelimit.blocked",
                    path=request.url.path, prefix=prefix,
                    limit=limit, window=window, retry_after=retry_after,
                )
                # Returned, not raised — see the module docstring.
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Too many requests. Please slow down.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)

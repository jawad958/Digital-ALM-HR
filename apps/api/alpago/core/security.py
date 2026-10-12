"""Security primitives — password hashing + JWT access tokens.

Internal staff auth: email + bcrypt password → HS256 JWT signed with AUTH_SECRET.
`sub` claim holds the user id. Candidates get magic-link tokens elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from alpago.core.config import settings


ALGORITHM = "HS256"

# One week — fine for an internal tool.
DEFAULT_TOKEN_TTL = timedelta(days=7)


# ─── passwords ──────────────────────────────────────────────────────────────
# Using the `bcrypt` library directly rather than passlib — passlib's startup
# self-test uses a > 72-byte secret, which bcrypt 4.x refuses.

def _to_bytes(plain: str) -> bytes:
    # bcrypt caps at 72 bytes. Truncate to stay compatible with bcrypt 4.x.
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT (new) ──────────────────────────────────────────────────────────────

def create_access_token(
    user_id: UUID | str,
    *,
    email: str | None = None,
    ttl: timedelta = DEFAULT_TOKEN_TTL,
) -> str:
    now = datetime.now(tz=timezone.utc)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": "alpago-hr",
    }
    if email:
        claims["email"] = email
    return jwt.encode(claims, settings.auth_secret, algorithm=ALGORITHM)


def verify_access_token(token: str) -> dict[str, Any]:
    """Decode + validate a JWT we issued. Raises jose.JWTError on failure."""
    return jwt.decode(
        token,
        settings.auth_secret,
        algorithms=[ALGORITHM],
        issuer="alpago-hr",
        options={"require": ["exp", "iat", "sub"]},
    )


# ─── legacy exports (kept for callers that haven't migrated yet) ────────────

class InvalidToken(Exception):
    """Legacy exception kept for callers that still catch it."""


class SessionClaims(BaseModel):
    """Legacy shape — still used by a couple of callers."""
    sub: str
    email: str | None = None
    name: str | None = None
    iat: int
    exp: int

    @property
    def expired(self) -> bool:
        return datetime.now(tz=timezone.utc).timestamp() > self.exp


def verify_session_token(token: str) -> SessionClaims:
    """Backward-compat wrapper around verify_access_token."""
    try:
        payload = verify_access_token(token)
    except JWTError as e:
        raise InvalidToken(str(e)) from e
    return SessionClaims(**{k: payload.get(k) for k in ("sub", "email", "name", "iat", "exp")})


def email_domain_allowed(email: str) -> bool:
    """Staff sign-in restricted to configured domains. Candidates use magic links."""
    try:
        _, domain = email.lower().split("@", 1)
    except ValueError:
        return False
    return domain in settings.allowed_domains

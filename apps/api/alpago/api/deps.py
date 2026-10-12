"""FastAPI dependencies — auth + db + current user.

Auth is simple: a JWT in the Authorization header, signed with AUTH_SECRET.
The token's `sub` claim is the user id. See `alpago.core.security`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alpago.core.database import get_db
from alpago.core.security import verify_access_token
from alpago.models.role import Role, UserRole
from alpago.models.user import User, UserStatus


def _unauth(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_claims(authorization: str | None = Header(default=None)) -> dict:
    """Parse the Bearer token and return its claims. Does not touch DB."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauth("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise _unauth("missing bearer token")
    try:
        return verify_access_token(token)
    except ExpiredSignatureError:
        raise _unauth("token expired")
    except JWTError as e:
        raise _unauth(f"invalid token: {e}")


async def current_user(
    claims: Annotated[dict, Depends(current_claims)],
    db: AsyncSession = Depends(get_db),
) -> User:
    sub = claims.get("sub")
    if not sub:
        raise _unauth("invalid token: no sub")
    try:
        user_id = UUID(sub)
    except (ValueError, TypeError):
        raise _unauth("invalid token: bad sub")

    user = await db.get(User, user_id)
    if user is None:
        raise _unauth("user not provisioned")
    if user.status != UserStatus.active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"account is {user.status.value}",
        )
    return user


async def current_user_with_roles(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, list[Role]]:
    stmt = (
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .options(selectinload(UserRole.role))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return user, [r.role for r in rows]


def require_roles(*required: str):
    """Dependency factory: caller must hold at least one of the required roles."""

    async def _check(
        user_roles: Annotated[tuple[User, list[Role]], Depends(current_user_with_roles)],
    ) -> User:
        user, roles = user_roles
        if not any(r.key in required for r in roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"requires one of: {', '.join(required)}",
            )
        return user

    return _check

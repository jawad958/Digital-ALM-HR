"""Auth endpoints — simple JWT + email/password.

  POST /auth/register   create a user (open now for seeding; lock down later)
  POST /auth/login      exchange email+password for a JWT
  GET  /auth/me         return the authenticated user + roles
  GET  /auth/users      everyone who can sign in, with their roles
  GET  /auth/roles      the role catalogue
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alpago.api.deps import current_user_with_roles, get_db, require_roles
from alpago.core.audit import record_audit
from alpago.core.security import (
    DEFAULT_TOKEN_TTL,
    create_access_token,
    hash_password,
    verify_password,
)
from alpago.models.role import Role, UserRole
from alpago.models.user import AuthProvider, User, UserStatus
from alpago.schemas.user import MeResponse, RoleOut, UserOut


router = APIRouter(prefix="/auth", tags=["auth"])


# ─── schemas ────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = int(DEFAULT_TOKEN_TTL.total_seconds())
    user: UserOut
    roles: list[RoleOut] = []


# ─── routes ─────────────────────────────────────────────────────────────────

async def _user_roles(db: AsyncSession, user_id) -> list[Role]:
    stmt = (
        select(UserRole)
        .where(UserRole.user_id == user_id)
        .options(selectinload(UserRole.role))
    )
    return [ur.role for ur in (await db.execute(stmt)).scalars().all()]


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()

    # Uniform error — don't leak whether the email exists
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}",
        )

    user.last_login_at = datetime.now(tz=timezone.utc)
    await db.flush()

    roles = await _user_roles(db, user.id)
    token = create_access_token(user.id, email=user.email)
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
        roles=[RoleOut.model_validate(r) for r in roles],
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        name=body.name,
        status=UserStatus.active,
        auth_provider=AuthProvider.password,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    token = create_access_token(user.id, email=user.email)
    return TokenOut(
        access_token=token,
        user=UserOut.model_validate(user),
        roles=[],
    )


@router.get("/me", response_model=MeResponse)
async def me(
    user_roles: Annotated[tuple[User, list[Role]], Depends(current_user_with_roles)],
) -> MeResponse:
    user, roles = user_roles
    return MeResponse.model_validate({"user": user, "roles": roles})


class UserWithRoles(BaseModel):
    id: UUID
    email: EmailStr
    name: str | None = None
    status: str
    last_login_at: datetime | None = None
    roles: list[RoleOut] = []


@router.get("/users", response_model=list[UserWithRoles])
async def list_users(
    _: Annotated[tuple[User, list[Role]], Depends(current_user_with_roles)],
    db: AsyncSession = Depends(get_db),
) -> list[UserWithRoles]:
    """Everyone who can sign in, with their assigned roles."""
    users = (
        await db.execute(select(User).order_by(User.email))
    ).scalars().all()

    links = (
        await db.execute(select(UserRole).options(selectinload(UserRole.role)))
    ).scalars().all()

    by_user: dict[UUID, list[Role]] = {}
    for link in links:
        by_user.setdefault(link.user_id, []).append(link.role)

    return [
        UserWithRoles(
            id=u.id, email=u.email, name=u.name,
            status=u.status.value if hasattr(u.status, "value") else str(u.status),
            last_login_at=u.last_login_at,
            roles=[RoleOut.model_validate(r) for r in by_user.get(u.id, [])],
        )
        for u in users
    ]


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _: Annotated[tuple[User, list[Role]], Depends(current_user_with_roles)],
    db: AsyncSession = Depends(get_db),
) -> list[Role]:
    return list((await db.execute(select(Role).order_by(Role.name))).scalars().all())


class SetRolesIn(BaseModel):
    role_keys: list[str] = Field(default_factory=list)


@router.put("/users/{user_id}/roles", response_model=UserWithRoles)
async def set_user_roles(
    user_id: UUID,
    body: SetRolesIn,
    actor: Annotated[User, Depends(require_roles("admin", "hr_lead"))],
    db: AsyncSession = Depends(get_db),
) -> UserWithRoles:
    """Replace a user's roles with exactly the set given. Admin / HR lead only."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    wanted = {k.strip() for k in body.role_keys if k.strip()}
    roles = (
        await db.execute(select(Role).where(Role.key.in_(wanted)))
    ).scalars().all() if wanted else []

    found = {r.key for r in roles}
    missing = wanted - found
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown role keys: {', '.join(sorted(missing))}",
        )

    current_links = (
        await db.execute(select(UserRole).where(UserRole.user_id == user_id))
    ).scalars().all()
    before = sorted({link.role_id for link in current_links})

    # Don't let the last admin strip their own admin role and lock everyone out
    if target.id == actor.id and "admin" not in found:
        actor_is_admin = (await db.execute(
            select(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == actor.id, Role.key == "admin")
        )).scalar_one_or_none()
        if actor_is_admin is not None:
            other_admins = (await db.execute(
                select(func.count(UserRole.id))
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.key == "admin", UserRole.user_id != actor.id)
            )).scalar_one()
            if other_admins == 0:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "You are the only administrator — assign admin to someone else first.",
                )

    for link in current_links:
        await db.delete(link)
    await db.flush()

    for r in roles:
        db.add(UserRole(user_id=user_id, role_id=r.id, scope_key=None, scope={}))
    await db.flush()

    await record_audit(
        db, actor=actor, action="user.roles_changed",
        subject_type="user", subject_id=target.id,
        before={"role_ids": [str(x) for x in before]},
        after={"roles": sorted(found)},
        context={"target_email": target.email},
    )

    return UserWithRoles(
        id=target.id, email=target.email, name=target.name,
        status=target.status.value if hasattr(target.status, "value") else str(target.status),
        last_login_at=target.last_login_at,
        roles=[RoleOut.model_validate(r) for r in roles],
    )

"""User — everyone who signs into the platform (staff + candidates)."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alpago.models.base import Auditable, Base, Timestamps, UUIDPK

if TYPE_CHECKING:
    from alpago.models.role import UserRole


class UserStatus(str, Enum):
    active = "active"
    invited = "invited"
    suspended = "suspended"


class AuthProvider(str, Enum):
    password = "password"       # internal staff login (email + password)
    google = "google"
    microsoft = "microsoft"
    magic_link = "magic_link"   # candidates


class User(Base, UUIDPK, Timestamps, Auditable):
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(200))

    # native_enum=False → stored as VARCHAR, works on SQLite and Postgres identically
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, native_enum=False, length=20),
        default=UserStatus.active,
        nullable=False,
    )
    auth_provider: Mapped[AuthProvider | None] = mapped_column(
        SAEnum(AuthProvider, native_enum=False, length=20),
        nullable=True,
    )
    # Bcrypt hash of the password for internal staff. NULL for OAuth / magic-link users.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="UserRole.user_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"

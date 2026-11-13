from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import UnauthorizedError, ConflictError, NotFoundError, ForbiddenError
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User, Role, UserRole
from app.models.system import RefreshToken, AuditLog
from app.schemas.auth import UserRegister, UserLogin, Token, ChangePassword


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserRegister, ip: Optional[str] = None) -> User:
        result = await self.db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise ConflictError("Email already registered")

        role_result = await self.db.execute(select(Role).where(Role.name == UserRole.CUSTOMER))
        role = role_result.scalar_one_or_none()
        if not role:
            role = Role(name=UserRole.CUSTOMER, description="Customer")
            self.db.add(role)
            await self.db.flush()

        user = User(
            email=data.email.lower(),
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            phone=data.phone,
            role_id=role.id,
            is_active=True,
            is_verified=True,
        )
        self.db.add(user)
        await self.db.flush()

        await self._audit(user.id, "REGISTER", "user", user.id, ip)
        await self.db.commit()
        await self.db.refresh(user, attribute_names=["role"])
        return user

    async def login(self, data: UserLogin, ip: Optional[str] = None) -> Token:
        result = await self.db.execute(
            select(User).options(selectinload(User.role)).where(User.email == data.email.lower())
        )
        user = result.scalar_one_or_none()
        if not user or not verify_password(data.password, user.hashed_password):
            await self._audit(None, "FAILED_LOGIN", "user", None, ip, {"email": data.email})
            raise UnauthorizedError("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedError("Account is inactive")

        access = create_access_token(str(user.id))
        refresh = create_refresh_token(str(user.id))
        expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        rt = RefreshToken(user_id=user.id, token=refresh, expires_at=expires)
        self.db.add(rt)
        user.last_login = datetime.now(timezone.utc)
        await self._audit(user.id, "LOGIN", "user", user.id, ip)
        await self.db.commit()
        return Token(access_token=access, refresh_token=refresh)

    async def refresh(self, refresh_token: str) -> Token:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")

        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token == refresh_token,
                RefreshToken.is_revoked == False,  # noqa: E712
            )
        )
        stored = result.scalar_one_or_none()
        if not stored or stored.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token expired or revoked")

        # Rotate
        stored.is_revoked = True
        user_id = stored.user_id
        access = create_access_token(str(user_id))
        new_refresh = create_refresh_token(str(user_id))
        expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.db.add(RefreshToken(user_id=user_id, token=new_refresh, expires_at=expires))
        await self.db.commit()
        return Token(access_token=access, refresh_token=new_refresh)

    async def logout(self, refresh_token: str, user_id: UUID) -> None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token == refresh_token,
                RefreshToken.user_id == user_id,
            )
        )
        stored = result.scalar_one_or_none()
        if stored:
            stored.is_revoked = True
            await self.db.commit()

    async def change_password(self, user: User, data: ChangePassword) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise UnauthorizedError("Current password is incorrect")
        user.hashed_password = get_password_hash(data.new_password)
        # Revoke all refresh tokens
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .values(is_revoked=True)
        )
        await self.db.commit()

    async def get_me(self, user: User) -> User:
        return user

    async def _audit(
        self,
        user_id: Optional[UUID],
        action: str,
        entity: Optional[str],
        entity_id: Optional[UUID],
        ip: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip_address=ip,
            metadata_=metadata,
        )
        self.db.add(log)
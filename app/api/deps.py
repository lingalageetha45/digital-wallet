from typing import Annotated, Optional
from uuid import UUID
from fastapi import Depends, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import UnauthorizedError, ForbiddenError, NotFoundError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.wallet import Wallet

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not credentials:
        raise UnauthorizedError("Not authenticated")
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(
        select(User).options(selectinload(User.role)).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")
    if not user.is_active:
        raise UnauthorizedError("Inactive user")
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise UnauthorizedError("Inactive user")
    return current_user


def require_roles(*roles: UserRole):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role.name not in roles:
            raise ForbiddenError(f"Requires one of roles: {[r.value for r in roles]}")
        return current_user

    return role_checker


RequireAdmin = require_roles(UserRole.SUPER_ADMIN, UserRole.ADMIN)
RequireSupport = require_roles(UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT)
RequireSuperAdmin = require_roles(UserRole.SUPER_ADMIN)


async def get_wallet_for_user(
    wallet_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.id == wallet_id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise NotFoundError("Wallet not found")
    # Admins/Support can access any wallet
    if current_user.role.name in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
        return wallet
    if wallet.user_id != current_user.id:
        raise ForbiddenError("You do not own this wallet")
    return wallet


async def get_idempotency_key(
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
) -> Optional[str]:
    return idempotency_key


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_client_ip
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    Token,
    RefreshTokenRequest,
    ChangePassword,
    UserResponse,
)
from app.schemas.common import ResponseModel, MessageResponse
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=ResponseModel[UserResponse], status_code=201)
async def register(
    data: UserRegister,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AuthService(db)
    user = await service.register(data, ip=get_client_ip(request))
    return ResponseModel(
        data=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            is_active=user.is_active,
            is_verified=user.is_verified,
            role=user.role_name,
            created_at=user.created_at,
            last_login=user.last_login,
        )
    )


@router.post("/login", response_model=ResponseModel[Token])
async def login(
    data: UserLogin,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AuthService(db)
    token = await service.login(data, ip=get_client_ip(request))
    return ResponseModel(data=token)


@router.post("/refresh", response_model=ResponseModel[Token])
async def refresh(
    data: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AuthService(db)
    token = await service.refresh(data.refresh_token)
    return ResponseModel(data=token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshTokenRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AuthService(db)
    await service.logout(data.refresh_token, current_user.id)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=ResponseModel[UserResponse])
async def me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return ResponseModel(
        data=UserResponse(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            phone=current_user.phone,
            is_active=current_user.is_active,
            is_verified=current_user.is_verified,
            role=current_user.role_name,
            created_at=current_user.created_at,
            last_login=current_user.last_login,
        )
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    data: ChangePassword,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AuthService(db)
    await service.change_password(current_user, data)
    return MessageResponse(message="Password changed successfully")
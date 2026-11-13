from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequireAdmin, RequireSupport, get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import (
    TransactionLimitOut,
    TransactionLimitUpdate,
    DashboardAdmin,
    DashboardSupport,
    DashboardCustomer,
)
from app.schemas.common import ResponseModel
from app.services.admin_service import AdminService

router = APIRouter()


@router.get("/transaction-limits", response_model=ResponseModel[TransactionLimitOut])
async def get_limits(
    current_user: Annotated[User, Depends(RequireAdmin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AdminService(db)
    limits = await service.get_or_create_limits()
    return ResponseModel(data=TransactionLimitOut.model_validate(limits))


@router.patch("/transaction-limits", response_model=ResponseModel[TransactionLimitOut])
async def update_limits(
    data: TransactionLimitUpdate,
    current_user: Annotated[User, Depends(RequireAdmin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AdminService(db)
    limits = await service.update_limits(current_user, data)
    return ResponseModel(data=TransactionLimitOut.model_validate(limits))


@router.get("/dashboard", response_model=ResponseModel[DashboardAdmin])
async def admin_dashboard(
    current_user: Annotated[User, Depends(RequireAdmin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AdminService(db)
    data = await service.admin_dashboard()
    return ResponseModel(data=data)


@router.get("/support-dashboard", response_model=ResponseModel[DashboardSupport])
async def support_dashboard(
    current_user: Annotated[User, Depends(RequireSupport)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AdminService(db)
    data = await service.support_dashboard()
    return ResponseModel(data=data)


@router.get("/my-dashboard", response_model=ResponseModel[DashboardCustomer])
async def customer_dashboard(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = AdminService(db)
    data = await service.customer_dashboard(current_user)
    return ResponseModel(data=data)
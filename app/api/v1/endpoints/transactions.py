from typing import Annotated, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, RequireSupport
from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import (
    TransferCreate,
    TransferOut,
    DepositOut,
    WithdrawalOut,
    RefundCreate,
    RefundOut,
    LedgerOut,
)
from app.schemas.common import ResponseModel, PaginatedResponse, MessageResponse
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.post("/transfers", response_model=ResponseModel[TransferOut], status_code=201)
async def create_transfer(
    data: TransferCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    service = TransactionService(db)
    transfer = await service.create_transfer(current_user, data, idempotency_key)
    return ResponseModel(data=TransferOut.model_validate(transfer))


@router.get("/transfers", response_model=ResponseModel[List[TransferOut]])
async def list_transfers(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = TransactionService(db)
    items = await service.list_transfers(current_user)
    return ResponseModel(data=[TransferOut.model_validate(t) for t in items])


@router.get("/deposits", response_model=ResponseModel[List[DepositOut]])
async def list_deposits(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    wallet_id: Optional[UUID] = None,
):
    service = TransactionService(db)
    items = await service.list_deposits(current_user, wallet_id)
    return ResponseModel(data=[DepositOut.model_validate(d) for d in items])


@router.get("/withdrawals", response_model=ResponseModel[List[WithdrawalOut]])
async def list_withdrawals(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    wallet_id: Optional[UUID] = None,
):
    service = TransactionService(db)
    items = await service.list_withdrawals(current_user, wallet_id)
    return ResponseModel(data=[WithdrawalOut.model_validate(w) for w in items])


@router.post("/refunds", response_model=ResponseModel[RefundOut], status_code=201)
async def create_refund(
    data: RefundCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = TransactionService(db)
    refund = await service.create_refund(current_user, data)
    return ResponseModel(data=RefundOut.model_validate(refund))


@router.post("/refunds/{refund_id}/approve", response_model=ResponseModel[RefundOut])
async def approve_refund(
    refund_id: UUID,
    current_user: Annotated[User, Depends(RequireSupport)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = TransactionService(db)
    refund = await service.approve_refund(refund_id, current_user)
    return ResponseModel(data=RefundOut.model_validate(refund))


@router.post("/refunds/{refund_id}/reject", response_model=ResponseModel[RefundOut])
async def reject_refund(
    refund_id: UUID,
    current_user: Annotated[User, Depends(RequireSupport)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = TransactionService(db)
    refund = await service.reject_refund(refund_id, current_user)
    return ResponseModel(data=RefundOut.model_validate(refund))


@router.get("/transactions", response_model=PaginatedResponse[LedgerOut])
async def list_transactions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    wallet_id: Optional[UUID] = None,
    type: Optional[str] = None,
):
    service = TransactionService(db)
    items, total = await service.list_ledger(current_user, wallet_id, page, page_size, type)
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return PaginatedResponse(
        data=[LedgerOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
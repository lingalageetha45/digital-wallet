from typing import Annotated, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, RequireAdmin, RequireSupport
from app.db.session import get_db
from app.models.user import User
from app.schemas.wallet import WalletCreate, WalletUpdate, WalletOut, WalletFreezeRequest
from app.schemas.common import ResponseModel, MessageResponse
from app.schemas.transaction import DepositCreate, DepositOut, WithdrawalCreate, WithdrawalOut
from app.services.wallet_service import WalletService
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.post("", response_model=ResponseModel[WalletOut], status_code=201)
async def create_wallet(
    data: WalletCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallet = await service.create_wallet(current_user, data)
    return ResponseModel(data=WalletOut.model_validate(wallet))


@router.get("", response_model=ResponseModel[List[WalletOut]])
async def list_wallets(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallets = await service.list_wallets(current_user)
    return ResponseModel(data=[WalletOut.model_validate(w) for w in wallets])


@router.get("/{wallet_id}", response_model=ResponseModel[WalletOut])
async def get_wallet(
    wallet_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallet = await service.get_wallet(wallet_id, current_user)
    return ResponseModel(data=WalletOut.model_validate(wallet))


@router.patch("/{wallet_id}", response_model=ResponseModel[WalletOut])
async def update_wallet(
    wallet_id: UUID,
    data: WalletUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallet = await service.update_wallet(wallet_id, current_user, data)
    return ResponseModel(data=WalletOut.model_validate(wallet))


@router.post("/{wallet_id}/freeze", response_model=ResponseModel[WalletOut])
async def freeze_wallet(
    wallet_id: UUID,
    data: WalletFreezeRequest,
    current_user: Annotated[User, Depends(RequireSupport)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallet = await service.freeze_wallet(wallet_id, current_user, data.reason)
    return ResponseModel(data=WalletOut.model_validate(wallet))


@router.post("/{wallet_id}/unfreeze", response_model=ResponseModel[WalletOut])
async def unfreeze_wallet(
    wallet_id: UUID,
    current_user: Annotated[User, Depends(RequireSupport)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = WalletService(db)
    wallet = await service.unfreeze_wallet(wallet_id, current_user)
    return ResponseModel(data=WalletOut.model_validate(wallet))


@router.post("/{wallet_id}/deposits", response_model=ResponseModel[DepositOut], status_code=201)
async def create_deposit(
    wallet_id: UUID,
    data: DepositCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    service = TransactionService(db)
    deposit = await service.create_deposit(wallet_id, current_user, data, idempotency_key)
    return ResponseModel(data=DepositOut.model_validate(deposit))


@router.post("/{wallet_id}/withdrawals", response_model=ResponseModel[WithdrawalOut], status_code=201)
async def create_withdrawal(
    wallet_id: UUID,
    data: WithdrawalCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
):
    service = TransactionService(db)
    withdrawal = await service.create_withdrawal(wallet_id, current_user, data, idempotency_key)
    return ResponseModel(data=WithdrawalOut.model_validate(withdrawal))
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.transaction import (
    DepositStatus,
    WithdrawalStatus,
    TransferStatus,
    RefundStatus,
    TransactionType,
)


class DepositCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    description: Optional[str] = None


class DepositOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wallet_id: UUID
    amount: Decimal
    currency: str
    status: DepositStatus
    reference_number: str
    description: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class WithdrawalCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    bank_account: Optional[str] = None
    description: Optional[str] = None


class WithdrawalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wallet_id: UUID
    amount: Decimal
    currency: str
    status: WithdrawalStatus
    reference_number: str
    bank_account: Optional[str]
    description: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class TransferCreate(BaseModel):
    sender_wallet_id: UUID
    receiver_wallet_id: UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    description: Optional[str] = None


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_wallet_id: UUID
    receiver_wallet_id: UUID
    amount: Decimal
    currency: str
    status: TransferStatus
    reference_number: str
    description: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class RefundCreate(BaseModel):
    original_transaction_type: str  # deposit, transfer, withdrawal
    original_transaction_id: UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    reason: Optional[str] = None


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_transaction_type: str
    original_transaction_id: UUID
    wallet_id: UUID
    amount: Decimal
    currency: str
    status: RefundStatus
    reason: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wallet_id: UUID
    transaction_type: TransactionType
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    reference_entity: str
    reference_id: UUID
    description: Optional[str]
    created_at: datetime


class TransactionLimitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    max_transaction_amount: Decimal
    daily_transfer_limit: Decimal
    daily_withdrawal_limit: Decimal
    max_transactions_per_day: int
    suspicious_amount_threshold: Decimal
    updated_at: datetime


class TransactionLimitUpdate(BaseModel):
    max_transaction_amount: Optional[Decimal] = Field(None, gt=0)
    daily_transfer_limit: Optional[Decimal] = Field(None, gt=0)
    daily_withdrawal_limit: Optional[Decimal] = Field(None, gt=0)
    max_transactions_per_day: Optional[int] = Field(None, gt=0)
    suspicious_amount_threshold: Optional[Decimal] = Field(None, gt=0)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    message: str
    notification_type: str
    is_read: bool
    reference_entity: Optional[str]
    reference_id: Optional[UUID]
    created_at: datetime


class DashboardAdmin(BaseModel):
    total_users: int
    active_wallets: int
    total_wallet_balance: Decimal
    todays_transactions: int
    todays_transaction_volume: Decimal
    failed_transactions: int
    suspicious_transactions: int


class DashboardSupport(BaseModel):
    pending_reviews: int
    suspicious_transactions: int
    failed_transactions: int
    refund_requests: int
    frozen_wallets: int


class DashboardCustomer(BaseModel):
    wallet_balance: Decimal
    recent_transactions: list
    total_deposits: Decimal
    total_transfers: Decimal
    total_withdrawals: Decimal
    pending_transactions: int
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ForbiddenError
from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletStatus
from app.models.transaction import (
    Deposit,
    Withdrawal,
    Transfer,
    TransactionLedger,
    Refund,
    DepositStatus,
    WithdrawalStatus,
    TransferStatus,
    RefundStatus,
)
from app.models.system import TransactionLimit, SuspiciousTransaction, SuspiciousFlag, AuditLog
from app.schemas.transaction import TransactionLimitUpdate, DashboardAdmin, DashboardSupport, DashboardCustomer
from app.core.config import settings


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_limits(self) -> TransactionLimit:
        result = await self.db.execute(select(TransactionLimit).limit(1))
        limits = result.scalar_one_or_none()
        if not limits:
            limits = TransactionLimit(
                max_transaction_amount=Decimal(str(settings.MAX_TRANSACTION_AMOUNT)),
                daily_transfer_limit=Decimal(str(settings.DAILY_TRANSFER_LIMIT)),
                daily_withdrawal_limit=Decimal(str(settings.DAILY_WITHDRAWAL_LIMIT)),
                max_transactions_per_day=settings.MAX_TRANSACTIONS_PER_DAY,
                suspicious_amount_threshold=Decimal(str(settings.SUSPICIOUS_AMOUNT_THRESHOLD)),
            )
            self.db.add(limits)
            await self.db.commit()
            await self.db.refresh(limits)
        return limits

    async def update_limits(self, actor: User, data: TransactionLimitUpdate) -> TransactionLimit:
        if actor.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN):
            raise ForbiddenError("Only admins can update limits")
        limits = await self.get_or_create_limits()
        if data.max_transaction_amount is not None:
            limits.max_transaction_amount = data.max_transaction_amount
        if data.daily_transfer_limit is not None:
            limits.daily_transfer_limit = data.daily_transfer_limit
        if data.daily_withdrawal_limit is not None:
            limits.daily_withdrawal_limit = data.daily_withdrawal_limit
        if data.max_transactions_per_day is not None:
            limits.max_transactions_per_day = data.max_transactions_per_day
        if data.suspicious_amount_threshold is not None:
            limits.suspicious_amount_threshold = data.suspicious_amount_threshold
        limits.updated_by = actor.id
        self.db.add(
            AuditLog(
                user_id=actor.id,
                action="TRANSACTION_LIMIT_CHANGED",
                entity="transaction_limits",
                entity_id=limits.id,
                metadata_=data.model_dump(exclude_none=True),
            )
        )
        await self.db.commit()
        await self.db.refresh(limits)
        return limits

    async def admin_dashboard(self) -> DashboardAdmin:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        total_users = (await self.db.execute(select(func.count()).select_from(User))).scalar() or 0
        active_wallets = (
            await self.db.execute(
                select(func.count()).select_from(Wallet).where(Wallet.status == WalletStatus.ACTIVE)
            )
        ).scalar() or 0
        total_balance = (
            await self.db.execute(select(func.coalesce(func.sum(Wallet.available_balance), 0)))
        ).scalar() or Decimal("0")

        todays_tx = (
            await self.db.execute(
                select(func.count())
                .select_from(TransactionLedger)
                .where(TransactionLedger.created_at >= today_start)
            )
        ).scalar() or 0
        todays_volume = (
            await self.db.execute(
                select(func.coalesce(func.sum(TransactionLedger.amount), 0)).where(
                    TransactionLedger.created_at >= today_start
                )
            )
        ).scalar() or Decimal("0")

        failed = (
            await self.db.execute(
                select(func.count()).select_from(Transfer).where(Transfer.status == TransferStatus.FAILED)
            )
        ).scalar() or 0
        suspicious = (
            await self.db.execute(
                select(func.count())
                .select_from(SuspiciousTransaction)
                .where(SuspiciousTransaction.flag == SuspiciousFlag.REVIEW_REQUIRED)
            )
        ).scalar() or 0

        return DashboardAdmin(
            total_users=total_users,
            active_wallets=active_wallets,
            total_wallet_balance=total_balance,
            todays_transactions=todays_tx,
            todays_transaction_volume=todays_volume,
            failed_transactions=failed,
            suspicious_transactions=suspicious,
        )

    async def support_dashboard(self) -> DashboardSupport:
        pending_reviews = (
            await self.db.execute(
                select(func.count())
                .select_from(SuspiciousTransaction)
                .where(SuspiciousTransaction.flag == SuspiciousFlag.REVIEW_REQUIRED)
            )
        ).scalar() or 0
        suspicious = pending_reviews
        failed = (
            await self.db.execute(
                select(func.count()).select_from(Transfer).where(Transfer.status == TransferStatus.FAILED)
            )
        ).scalar() or 0
        refunds = (
            await self.db.execute(
                select(func.count())
                .select_from(Refund)
                .where(Refund.status.in_([RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW]))
            )
        ).scalar() or 0
        frozen = (
            await self.db.execute(
                select(func.count()).select_from(Wallet).where(Wallet.status == WalletStatus.FROZEN)
            )
        ).scalar() or 0
        return DashboardSupport(
            pending_reviews=pending_reviews,
            suspicious_transactions=suspicious,
            failed_transactions=failed,
            refund_requests=refunds,
            frozen_wallets=frozen,
        )

    async def customer_dashboard(self, user: User) -> DashboardCustomer:
        result = await self.db.execute(select(Wallet).where(Wallet.user_id == user.id))
        wallets = list(result.scalars().all())
        balance = sum((w.available_balance for w in wallets), Decimal("0"))

        wallet_ids = [w.id for w in wallets]
        if not wallet_ids:
            return DashboardCustomer(
                wallet_balance=Decimal("0"),
                recent_transactions=[],
                total_deposits=Decimal("0"),
                total_transfers=Decimal("0"),
                total_withdrawals=Decimal("0"),
                pending_transactions=0,
            )

        recent = (
            await self.db.execute(
                select(TransactionLedger)
                .where(TransactionLedger.wallet_id.in_(wallet_ids))
                .order_by(TransactionLedger.created_at.desc())
                .limit(10)
            )
        ).scalars().all()

        total_deposits = (
            await self.db.execute(
                select(func.coalesce(func.sum(Deposit.amount), 0)).where(
                    Deposit.wallet_id.in_(wallet_ids), Deposit.status == DepositStatus.COMPLETED
                )
            )
        ).scalar() or Decimal("0")
        total_withdrawals = (
            await self.db.execute(
                select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                    Withdrawal.wallet_id.in_(wallet_ids), Withdrawal.status == WithdrawalStatus.COMPLETED
                )
            )
        ).scalar() or Decimal("0")
        total_transfers = (
            await self.db.execute(
                select(func.coalesce(func.sum(Transfer.amount), 0)).where(
                    Transfer.sender_wallet_id.in_(wallet_ids), Transfer.status == TransferStatus.COMPLETED
                )
            )
        ).scalar() or Decimal("0")
        pending = (
            await self.db.execute(
                select(func.count()).select_from(Transfer).where(
                    Transfer.sender_wallet_id.in_(wallet_ids),
                    Transfer.status.in_([TransferStatus.PENDING, TransferStatus.PROCESSING]),
                )
            )
        ).scalar() or 0

        return DashboardCustomer(
            wallet_balance=balance,
            recent_transactions=[
                {
                    "id": str(r.id),
                    "type": r.transaction_type.value,
                    "amount": str(r.amount),
                    "created_at": r.created_at.isoformat(),
                }
                for r in recent
            ],
            total_deposits=total_deposits,
            total_transfers=total_transfers,
            total_withdrawals=total_withdrawals,
            pending_transactions=pending,
        )
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import (
    InsufficientBalanceError,
    WalletFrozenError,
    WalletClosedError,
    InvalidTransferError,
    DuplicateTransactionError,
    TransactionLimitExceededError,
    DuplicateIdempotencyKeyError,
    InvalidRefundError,
    NotFoundError,
    ForbiddenError,
    ConflictError,
    AppException,
)
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
    TransactionType,
    LedgerStatus,
)
from app.models.system import (
    IdempotencyKey,
    TransactionLimit,
    SuspiciousTransaction,
    SuspiciousFlag,
    Notification,
    AuditLog,
)
from app.schemas.transaction import DepositCreate, WithdrawalCreate, TransferCreate, RefundCreate


def generate_reference(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8).upper()}"


class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ───────────────────────── Helpers ─────────────────────────

    async def _get_limits(self) -> TransactionLimit:
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
            await self.db.flush()
        return limits

    async def _check_idempotency(
        self, key: Optional[str], user_id: UUID, endpoint: str
    ) -> Optional[dict]:
        if not key:
            return None
        result = await self.db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key,
                IdempotencyKey.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            expires_at = existing.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at > datetime.now(timezone.utc):
                return existing.response_body
            # expired – allow reuse after cleanup
        return None

    async def _store_idempotency(
        self, key: str, user_id: UUID, endpoint: str, response_code: int, response_body: dict
    ) -> None:
        if not key:
            return
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        # Upsert-like behaviour
        result = await self.db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key, IdempotencyKey.user_id == user_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.response_code = response_code
            existing.response_body = response_body
            existing.expires_at = expires
        else:
            self.db.add(
                IdempotencyKey(
                    key=key,
                    user_id=user_id,
                    endpoint=endpoint,
                    response_code=response_code,
                    response_body=response_body,
                    expires_at=expires,
                )
            )

    async def _lock_wallet(self, wallet_id: UUID) -> Wallet:
        """SELECT ... FOR UPDATE to prevent concurrent modifications."""
        result = await self.db.execute(
            select(Wallet).where(Wallet.id == wallet_id).with_for_update()
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise NotFoundError("Wallet not found")
        return wallet

    def _assert_wallet_active(self, wallet: Wallet) -> None:
        if wallet.status == WalletStatus.FROZEN:
            raise WalletFrozenError()
        if wallet.status == WalletStatus.CLOSED:
            raise WalletClosedError()
        if wallet.status == WalletStatus.SUSPENDED:
            raise AppException(code="WALLET_SUSPENDED", message="Wallet is suspended.")

    async def _check_daily_limits(
        self, wallet: Wallet, amount: Decimal, op_type: str, limits: TransactionLimit
    ) -> None:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if op_type == "transfer":
            result = await self.db.execute(
                select(func.coalesce(func.sum(Transfer.amount), 0)).where(
                    Transfer.sender_wallet_id == wallet.id,
                    Transfer.status == TransferStatus.COMPLETED,
                    Transfer.created_at >= today_start,
                )
            )
            used = result.scalar() or Decimal("0")
            if used + amount > limits.daily_transfer_limit:
                raise TransactionLimitExceededError(
                    f"Daily transfer limit of {limits.daily_transfer_limit} exceeded."
                )
        elif op_type == "withdrawal":
            result = await self.db.execute(
                select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                    Withdrawal.wallet_id == wallet.id,
                    Withdrawal.status == WithdrawalStatus.COMPLETED,
                    Withdrawal.created_at >= today_start,
                )
            )
            used = result.scalar() or Decimal("0")
            if used + amount > limits.daily_withdrawal_limit:
                raise TransactionLimitExceededError(
                    f"Daily withdrawal limit of {limits.daily_withdrawal_limit} exceeded."
                )

        # Max transactions per day
        result = await self.db.execute(
            select(func.count()).select_from(TransactionLedger).where(
                TransactionLedger.wallet_id == wallet.id,
                TransactionLedger.created_at >= today_start,
            )
        )
        count = result.scalar() or 0
        if count >= limits.max_transactions_per_day:
            raise TransactionLimitExceededError("Maximum transactions per day exceeded.")

    async def _flag_suspicious(
        self,
        tx_type: str,
        tx_id: UUID,
        wallet_id: UUID,
        amount: Decimal,
        reason: str,
        flag: SuspiciousFlag = SuspiciousFlag.REVIEW_REQUIRED,
    ) -> None:
        self.db.add(
            SuspiciousTransaction(
                transaction_type=tx_type,
                transaction_id=tx_id,
                wallet_id=wallet_id,
                amount=amount,
                flag=flag,
                reason=reason,
            )
        )

    async def _notify(
        self,
        user_id: UUID,
        title: str,
        message: str,
        ntype: str,
        entity: Optional[str] = None,
        entity_id: Optional[UUID] = None,
    ) -> None:
        self.db.add(
            Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=ntype,
                reference_entity=entity,
                reference_id=entity_id,
            )
        )

    async def _audit(
        self,
        user_id: UUID,
        action: str,
        entity: str,
        entity_id: UUID,
        metadata: Optional[dict] = None,
    ) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                metadata_=metadata,
            )
        )

    def _create_ledger(
        self,
        wallet: Wallet,
        tx_type: TransactionType,
        amount: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        ref_entity: str,
        ref_id: UUID,
        created_by: UUID,
        description: Optional[str] = None,
    ) -> TransactionLedger:
        entry = TransactionLedger(
            wallet_id=wallet.id,
            transaction_type=tx_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_entity=ref_entity,
            reference_id=ref_id,
            description=description,
            status=LedgerStatus.POSTED,
            created_by=created_by,
        )
        self.db.add(entry)
        return entry

    # ───────────────────────── Deposit ─────────────────────────

    async def create_deposit(
        self,
        wallet_id: UUID,
        user: User,
        data: DepositCreate,
        idempotency_key: Optional[str] = None,
    ) -> Deposit:
        cached = await self._check_idempotency(idempotency_key, user.id, "create_deposit")
        if cached:
            # Return existing by reconstructing minimal response; caller will serialize
            raise DuplicateIdempotencyKeyError("Idempotent request already processed")

        limits = await self._get_limits()
        if data.amount > limits.max_transaction_amount:
            raise TransactionLimitExceededError(
                f"Amount exceeds maximum transaction limit of {limits.max_transaction_amount}"
            )

        wallet = await self._lock_wallet(wallet_id)
        if wallet.user_id != user.id and user.role.name not in (
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
        ):
            raise ForbiddenError("You do not own this wallet")
        self._assert_wallet_active(wallet)

        deposit = Deposit(
            wallet_id=wallet.id,
            amount=data.amount,
            currency=wallet.currency,
            status=DepositStatus.PROCESSING,
            reference_number=generate_reference("DEP"),
            description=data.description,
            created_by=user.id,
        )
        self.db.add(deposit)
        await self.db.flush()

        # Simulate instant success for demo (in real system this would be async / webhook)
        balance_before = wallet.available_balance
        wallet.available_balance += data.amount
        balance_after = wallet.available_balance
        deposit.status = DepositStatus.COMPLETED
        deposit.completed_at = datetime.now(timezone.utc)

        self._create_ledger(
            wallet,
            TransactionType.DEPOSIT,
            data.amount,
            balance_before,
            balance_after,
            "deposit",
            deposit.id,
            user.id,
            data.description or "Deposit",
        )

        if data.amount >= limits.suspicious_amount_threshold:
            await self._flag_suspicious(
                "deposit", deposit.id, wallet.id, data.amount, "Amount exceeds suspicious threshold"
            )

        await self._notify(
            wallet.user_id,
            "Deposit Completed",
            f"Deposit of {data.amount} {wallet.currency} completed. Ref: {deposit.reference_number}",
            "DEPOSIT_COMPLETED",
            "deposit",
            deposit.id,
        )
        await self._audit(user.id, "DEPOSIT_CREATED", "deposit", deposit.id)

        response_body = {
            "id": str(deposit.id),
            "reference_number": deposit.reference_number,
            "status": deposit.status.value,
            "amount": str(data.amount),
        }
        if idempotency_key:
            await self._store_idempotency(idempotency_key, user.id, "create_deposit", 201, response_body)

        await self.db.commit()
        await self.db.refresh(deposit)
        return deposit

    # ───────────────────────── Withdrawal ─────────────────────────

    async def create_withdrawal(
        self,
        wallet_id: UUID,
        user: User,
        data: WithdrawalCreate,
        idempotency_key: Optional[str] = None,
    ) -> Withdrawal:
        cached = await self._check_idempotency(idempotency_key, user.id, "create_withdrawal")
        if cached:
            raise DuplicateIdempotencyKeyError("Idempotent request already processed")

        limits = await self._get_limits()
        if data.amount > limits.max_transaction_amount:
            raise TransactionLimitExceededError(
                f"Amount exceeds maximum transaction limit of {limits.max_transaction_amount}"
            )

        wallet = await self._lock_wallet(wallet_id)
        if wallet.user_id != user.id and user.role.name not in (
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
        ):
            raise ForbiddenError("You do not own this wallet")
        self._assert_wallet_active(wallet)

        if wallet.available_balance < data.amount:
            raise InsufficientBalanceError()

        await self._check_daily_limits(wallet, data.amount, "withdrawal", limits)

        withdrawal = Withdrawal(
            wallet_id=wallet.id,
            amount=data.amount,
            currency=wallet.currency,
            status=WithdrawalStatus.PROCESSING,
            reference_number=generate_reference("WDR"),
            bank_account=data.bank_account,
            description=data.description,
            created_by=user.id,
        )
        self.db.add(withdrawal)
        await self.db.flush()

        balance_before = wallet.available_balance
        wallet.available_balance -= data.amount
        balance_after = wallet.available_balance
        withdrawal.status = WithdrawalStatus.COMPLETED
        withdrawal.completed_at = datetime.now(timezone.utc)

        self._create_ledger(
            wallet,
            TransactionType.WITHDRAWAL,
            data.amount,
            balance_before,
            balance_after,
            "withdrawal",
            withdrawal.id,
            user.id,
            data.description or "Withdrawal",
        )

        if data.amount >= limits.suspicious_amount_threshold:
            await self._flag_suspicious(
                "withdrawal",
                withdrawal.id,
                wallet.id,
                data.amount,
                "Amount exceeds suspicious threshold",
            )

        await self._notify(
            wallet.user_id,
            "Withdrawal Completed",
            f"Withdrawal of {data.amount} {wallet.currency} completed. Ref: {withdrawal.reference_number}",
            "WITHDRAWAL_COMPLETED",
            "withdrawal",
            withdrawal.id,
        )
        await self._audit(user.id, "WITHDRAWAL_CREATED", "withdrawal", withdrawal.id)

        if idempotency_key:
            await self._store_idempotency(
                idempotency_key,
                user.id,
                "create_withdrawal",
                201,
                {"id": str(withdrawal.id), "status": withdrawal.status.value},
            )

        await self.db.commit()
        await self.db.refresh(withdrawal)
        return withdrawal

    # ───────────────────────── Transfer ─────────────────────────

    async def create_transfer(
        self,
        user: User,
        data: TransferCreate,
        idempotency_key: Optional[str] = None,
    ) -> Transfer:
        cached = await self._check_idempotency(idempotency_key, user.id, "create_transfer")
        if cached:
            raise DuplicateIdempotencyKeyError("Idempotent request already processed")

        if data.sender_wallet_id == data.receiver_wallet_id:
            raise InvalidTransferError("Cannot transfer to the same wallet")

        limits = await self._get_limits()
        if data.amount > limits.max_transaction_amount:
            raise TransactionLimitExceededError(
                f"Amount exceeds maximum transaction limit of {limits.max_transaction_amount}"
            )

        # Lock both wallets in deterministic order to avoid deadlocks
        ids = sorted([data.sender_wallet_id, data.receiver_wallet_id], key=str)
        wallets = {}
        for wid in ids:
            wallets[wid] = await self._lock_wallet(wid)

        sender = wallets[data.sender_wallet_id]
        receiver = wallets[data.receiver_wallet_id]

        if sender.user_id != user.id and user.role.name not in (
            UserRole.SUPER_ADMIN,
            UserRole.ADMIN,
        ):
            raise ForbiddenError("You do not own the sender wallet")

        self._assert_wallet_active(sender)
        self._assert_wallet_active(receiver)

        if sender.currency != receiver.currency:
            raise InvalidTransferError("Currency mismatch between wallets")

        if sender.available_balance < data.amount:
            raise InsufficientBalanceError()

        await self._check_daily_limits(sender, data.amount, "transfer", limits)

        transfer = Transfer(
            sender_wallet_id=sender.id,
            receiver_wallet_id=receiver.id,
            amount=data.amount,
            currency=sender.currency,
            status=TransferStatus.PROCESSING,
            reference_number=generate_reference("TRF"),
            description=data.description,
            created_by=user.id,
        )
        self.db.add(transfer)
        await self.db.flush()

        # Atomic debit + credit
        sender_before = sender.available_balance
        sender.available_balance -= data.amount
        sender_after = sender.available_balance

        receiver_before = receiver.available_balance
        receiver.available_balance += data.amount
        receiver_after = receiver.available_balance

        transfer.status = TransferStatus.COMPLETED
        transfer.completed_at = datetime.now(timezone.utc)

        self._create_ledger(
            sender,
            TransactionType.TRANSFER_DEBIT,
            data.amount,
            sender_before,
            sender_after,
            "transfer",
            transfer.id,
            user.id,
            data.description or "Transfer debit",
        )
        self._create_ledger(
            receiver,
            TransactionType.TRANSFER_CREDIT,
            data.amount,
            receiver_before,
            receiver_after,
            "transfer",
            transfer.id,
            user.id,
            data.description or "Transfer credit",
        )

        if data.amount >= limits.suspicious_amount_threshold:
            await self._flag_suspicious(
                "transfer",
                transfer.id,
                sender.id,
                data.amount,
                "Amount exceeds suspicious threshold",
            )

        await self._notify(
            sender.user_id,
            "Transfer Completed",
            f"You sent {data.amount} {sender.currency}. Ref: {transfer.reference_number}",
            "TRANSFER_COMPLETED",
            "transfer",
            transfer.id,
        )
        await self._notify(
            receiver.user_id,
            "Transfer Received",
            f"You received {data.amount} {receiver.currency}. Ref: {transfer.reference_number}",
            "TRANSFER_RECEIVED",
            "transfer",
            transfer.id,
        )
        await self._audit(user.id, "TRANSFER_CREATED", "transfer", transfer.id)

        if idempotency_key:
            await self._store_idempotency(
                idempotency_key,
                user.id,
                "create_transfer",
                201,
                {"id": str(transfer.id), "status": transfer.status.value},
            )

        await self.db.commit()
        await self.db.refresh(transfer)
        return transfer

    # ───────────────────────── Refund ─────────────────────────

    async def create_refund(self, user: User, data: RefundCreate) -> Refund:
        # Basic validation – support deposit refunds for simplicity
        if data.original_transaction_type not in ("deposit", "transfer", "withdrawal"):
            raise InvalidRefundError("Unsupported original transaction type")

        wallet = None
        original_amount = Decimal("0")

        if data.original_transaction_type == "deposit":
            result = await self.db.execute(select(Deposit).where(Deposit.id == data.original_transaction_id))
            dep = result.scalar_one_or_none()
            if not dep or dep.status != DepositStatus.COMPLETED:
                raise InvalidRefundError("Original deposit not found or not completed")
            wallet = await self._lock_wallet(dep.wallet_id)
            original_amount = dep.amount
        else:
            raise InvalidRefundError("Only deposit refunds are supported in this version")

        if data.amount > original_amount:
            raise InvalidRefundError("Refund amount cannot exceed original transaction amount")

        # Prevent duplicate refunds (simple check)
        result = await self.db.execute(
            select(Refund).where(
                Refund.original_transaction_id == data.original_transaction_id,
                Refund.status.in_([RefundStatus.REQUESTED, RefundStatus.APPROVED, RefundStatus.COMPLETED]),
            )
        )
        if result.scalar_one_or_none():
            raise InvalidRefundError("A refund already exists for this transaction")

        self._assert_wallet_active(wallet)

        refund = Refund(
            original_transaction_type=data.original_transaction_type,
            original_transaction_id=data.original_transaction_id,
            wallet_id=wallet.id,
            amount=data.amount,
            currency=wallet.currency,
            status=RefundStatus.REQUESTED,
            reason=data.reason,
            created_by=user.id,
        )
        self.db.add(refund)
        await self.db.flush()
        await self._audit(user.id, "REFUND_CREATED", "refund", refund.id)
        await self.db.commit()
        await self.db.refresh(refund)
        return refund

    async def approve_refund(self, refund_id: UUID, actor: User) -> Refund:
        if actor.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            raise ForbiddenError("Not authorized to approve refunds")

        result = await self.db.execute(select(Refund).where(Refund.id == refund_id))
        refund = result.scalar_one_or_none()
        if not refund:
            raise NotFoundError("Refund not found")
        if refund.status not in (RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW):
            raise ConflictError(f"Cannot approve refund in status {refund.status.value}")

        wallet = await self._lock_wallet(refund.wallet_id)
        self._assert_wallet_active(wallet)

        # Credit the wallet (refund of a deposit = money back to user? Wait – deposit refund usually means reversing the credit)
        # For a deposit refund we DEBIT the wallet (take money back). For simplicity we treat refund as credit to available.
        # Business logic: refund of deposit → reverse the deposit → debit wallet.
        balance_before = wallet.available_balance
        if wallet.available_balance < refund.amount:
            raise InsufficientBalanceError("Insufficient balance to process refund debit")
        wallet.available_balance -= refund.amount
        balance_after = wallet.available_balance

        refund.status = RefundStatus.COMPLETED
        refund.reviewed_by = actor.id
        refund.reviewed_at = datetime.now(timezone.utc)
        refund.completed_at = datetime.now(timezone.utc)

        self._create_ledger(
            wallet,
            TransactionType.REFUND,
            refund.amount,
            balance_before,
            balance_after,
            "refund",
            refund.id,
            actor.id,
            refund.reason or "Refund processed",
        )
        await self._notify(
            wallet.user_id,
            "Refund Completed",
            f"Refund of {refund.amount} {wallet.currency} has been processed.",
            "REFUND_APPROVED",
            "refund",
            refund.id,
        )
        await self._audit(actor.id, "REFUND_APPROVED", "refund", refund.id)
        await self.db.commit()
        await self.db.refresh(refund)
        return refund

    async def reject_refund(self, refund_id: UUID, actor: User) -> Refund:
        if actor.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            raise ForbiddenError("Not authorized")
        result = await self.db.execute(select(Refund).where(Refund.id == refund_id))
        refund = result.scalar_one_or_none()
        if not refund:
            raise NotFoundError("Refund not found")
        if refund.status not in (RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW):
            raise ConflictError(f"Cannot reject refund in status {refund.status.value}")
        refund.status = RefundStatus.REJECTED
        refund.reviewed_by = actor.id
        refund.reviewed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(refund)
        return refund

    # ───────────────────────── Queries ─────────────────────────

    async def list_deposits(self, user: User, wallet_id: Optional[UUID] = None) -> List[Deposit]:
        q = select(Deposit).order_by(Deposit.created_at.desc())
        if user.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            # only own wallets
            subq = select(Wallet.id).where(Wallet.user_id == user.id)
            q = q.where(Deposit.wallet_id.in_(subq))
        if wallet_id:
            q = q.where(Deposit.wallet_id == wallet_id)
        result = await self.db.execute(q.limit(100))
        return list(result.scalars().all())

    async def list_withdrawals(self, user: User, wallet_id: Optional[UUID] = None) -> List[Withdrawal]:
        q = select(Withdrawal).order_by(Withdrawal.created_at.desc())
        if user.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            subq = select(Wallet.id).where(Wallet.user_id == user.id)
            q = q.where(Withdrawal.wallet_id.in_(subq))
        if wallet_id:
            q = q.where(Withdrawal.wallet_id == wallet_id)
        result = await self.db.execute(q.limit(100))
        return list(result.scalars().all())

    async def list_transfers(self, user: User) -> List[Transfer]:
        q = select(Transfer).order_by(Transfer.created_at.desc())
        if user.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            subq = select(Wallet.id).where(Wallet.user_id == user.id)
            q = q.where(
                (Transfer.sender_wallet_id.in_(subq)) | (Transfer.receiver_wallet_id.in_(subq))
            )
        result = await self.db.execute(q.limit(100))
        return list(result.scalars().all())

    async def list_ledger(
        self,
        user: User,
        wallet_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 20,
        tx_type: Optional[str] = None,
    ) -> Tuple[List[TransactionLedger], int]:
        q = select(TransactionLedger)
        count_q = select(func.count()).select_from(TransactionLedger)

        if user.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            subq = select(Wallet.id).where(Wallet.user_id == user.id)
            q = q.where(TransactionLedger.wallet_id.in_(subq))
            count_q = count_q.where(TransactionLedger.wallet_id.in_(subq))

        if wallet_id:
            q = q.where(TransactionLedger.wallet_id == wallet_id)
            count_q = count_q.where(TransactionLedger.wallet_id == wallet_id)
        if tx_type:
            try:
                t = TransactionType(tx_type.upper())
                q = q.where(TransactionLedger.transaction_type == t)
                count_q = count_q.where(TransactionLedger.transaction_type == t)
            except ValueError:
                pass

        total = (await self.db.execute(count_q)).scalar() or 0
        result = await self.db.execute(
            q.order_by(TransactionLedger.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total
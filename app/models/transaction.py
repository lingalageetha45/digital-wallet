import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# Use JSON with SQLite and JSONB with PostgreSQL.
JSONB = JSON().with_variant(PG_JSONB, "postgresql")


class DepositStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TransferStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RefundStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_DEBIT = "TRANSFER_DEBIT"
    TRANSFER_CREDIT = "TRANSFER_CREDIT"
    REFUND = "REFUND"
    FEE = "FEE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class LedgerStatus(str, enum.Enum):
    POSTED = "POSTED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="deposit_amount_positive"),
        Index("ix_deposits_wallet_id_status", "wallet_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[DepositStatus] = mapped_column(
        SAEnum(DepositStatus), default=DepositStatus.PENDING, nullable=False
    )
    reference_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="deposits")


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("amount > 0", name="withdrawal_amount_positive"),
        Index("ix_withdrawals_wallet_id_status", "wallet_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        SAEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING, nullable=False
    )
    reference_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    bank_account: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="withdrawals")


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="transfer_amount_positive"),
        Index("ix_transfers_sender_status", "sender_wallet_id", "status"),
        Index("ix_transfers_receiver_status", "receiver_wallet_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sender_wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    receiver_wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        SAEnum(TransferStatus), default=TransferStatus.PENDING, nullable=False
    )
    reference_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    sender_wallet: Mapped["Wallet"] = relationship(
        "Wallet", foreign_keys=[sender_wallet_id]
    )
    receiver_wallet: Mapped["Wallet"] = relationship(
        "Wallet", foreign_keys=[receiver_wallet_id]
    )


class TransactionLedger(Base):
    __tablename__ = "transaction_ledger"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ledger_amount_positive"),
        Index("ix_ledger_wallet_created", "wallet_id", "created_at"),
        Index("ix_ledger_reference", "reference_entity", "reference_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference_entity: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # deposit, transfer, withdrawal, refund
    reference_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LedgerStatus] = mapped_column(
        SAEnum(LedgerStatus), default=LedgerStatus.POSTED, nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    wallet: Mapped["Wallet"] = relationship(
        "Wallet", back_populates="ledger_entries"
    )


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="refund_amount_positive"),
        Index("ix_refunds_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_transaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # deposit/transfer/withdrawal
    original_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        SAEnum(RefundStatus), default=RefundStatus.REQUESTED, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet")


from app.models.wallet import Wallet  # noqa: E402
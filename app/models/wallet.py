import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WalletStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint(
            "available_balance >= 0",
            name="available_balance_non_negative",
        ),
        CheckConstraint(
            "pending_balance >= 0",
            name="pending_balance_non_negative",
        ),
        Index("ix_wallets_user_id_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="INR", nullable=False
    )
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    pending_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00"), nullable=False
    )
    status: Mapped[WalletStatus] = mapped_column(
        SAEnum(WalletStatus), default=WalletStatus.ACTIVE, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="wallets")
    deposits: Mapped[list["Deposit"]] = relationship(
        "Deposit", back_populates="wallet"
    )
    withdrawals: Mapped[list["Withdrawal"]] = relationship(
        "Withdrawal", back_populates="wallet"
    )
    ledger_entries: Mapped[list["TransactionLedger"]] = relationship(
        "TransactionLedger", back_populates="wallet"
    )

    @property
    def total_balance(self) -> Decimal:
        return self.available_balance + self.pending_balance


# Avoid circular imports
from app.models.user import User  # noqa: E402
from app.models.transaction import Deposit, TransactionLedger, Withdrawal  # noqa: E402
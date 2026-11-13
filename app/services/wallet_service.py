from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ForbiddenError, ConflictError, AppException
from app.models.user import User, UserRole
from app.models.wallet import Wallet, WalletStatus
from app.models.system import AuditLog, Notification
from app.schemas.wallet import WalletCreate, WalletUpdate


ALLOWED_TRANSITIONS = {
    WalletStatus.ACTIVE: {WalletStatus.FROZEN, WalletStatus.SUSPENDED, WalletStatus.CLOSED},
    WalletStatus.FROZEN: {WalletStatus.ACTIVE, WalletStatus.SUSPENDED, WalletStatus.CLOSED},
    WalletStatus.SUSPENDED: {WalletStatus.ACTIVE, WalletStatus.CLOSED},
    WalletStatus.CLOSED: set(),
}


class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_wallet(self, user: User, data: WalletCreate) -> Wallet:
        wallet = Wallet(
            user_id=user.id,
            currency=data.currency.upper(),
            name=data.name or f"{data.currency.upper()} Wallet",
            status=WalletStatus.ACTIVE,
        )
        self.db.add(wallet)
        await self.db.flush()
        await self._audit(user.id, "WALLET_CREATED", "wallet", wallet.id)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def list_wallets(self, user: User) -> List[Wallet]:
        if user.role.name in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            result = await self.db.execute(select(Wallet).order_by(Wallet.created_at.desc()))
        else:
            result = await self.db.execute(
                select(Wallet).where(Wallet.user_id == user.id).order_by(Wallet.created_at.desc())
            )
        return list(result.scalars().all())

    async def get_wallet(self, wallet_id: UUID, user: User) -> Wallet:
        result = await self.db.execute(select(Wallet).where(Wallet.id == wallet_id))
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise NotFoundError("Wallet not found")
        if user.role.name not in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT_AGENT):
            if wallet.user_id != user.id:
                raise ForbiddenError("You do not own this wallet")
        return wallet

    async def update_wallet(self, wallet_id: UUID, user: User, data: WalletUpdate) -> Wallet:
        wallet = await self.get_wallet(wallet_id, user)
        if data.name is not None:
            wallet.name = data.name
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def freeze_wallet(self, wallet_id: UUID, actor: User, reason: Optional[str] = None) -> Wallet:
        wallet = await self.get_wallet(wallet_id, actor)
        if wallet.status == WalletStatus.FROZEN:
            raise ConflictError("Wallet is already frozen")
        if wallet.status not in ALLOWED_TRANSITIONS or WalletStatus.FROZEN not in ALLOWED_TRANSITIONS.get(
            wallet.status, set()
        ):
            raise AppException(
                code="INVALID_STATUS_TRANSITION",
                message=f"Cannot freeze wallet from status {wallet.status.value}",
            )
        wallet.status = WalletStatus.FROZEN
        await self._audit(actor.id, "WALLET_FROZEN", "wallet", wallet.id, {"reason": reason})
        # Notify owner
        notif = Notification(
            user_id=wallet.user_id,
            title="Wallet Frozen",
            message=f"Your wallet {wallet.id} has been frozen." + (f" Reason: {reason}" if reason else ""),
            notification_type="WALLET_FROZEN",
            reference_entity="wallet",
            reference_id=wallet.id,
        )
        self.db.add(notif)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def unfreeze_wallet(self, wallet_id: UUID, actor: User) -> Wallet:
        wallet = await self.get_wallet(wallet_id, actor)
        if wallet.status != WalletStatus.FROZEN:
            raise ConflictError("Wallet is not frozen")
        wallet.status = WalletStatus.ACTIVE
        await self._audit(actor.id, "WALLET_UNFROZEN", "wallet", wallet.id)
        notif = Notification(
            user_id=wallet.user_id,
            title="Wallet Unfrozen",
            message=f"Your wallet {wallet.id} has been unfrozen and is now active.",
            notification_type="WALLET_UNFROZEN",
            reference_entity="wallet",
            reference_id=wallet.id,
        )
        self.db.add(notif)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

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
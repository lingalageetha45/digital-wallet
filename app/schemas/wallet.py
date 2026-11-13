from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.wallet import WalletStatus


class WalletCreate(BaseModel):
    currency: str = Field(default="INR", min_length=3, max_length=3)
    name: Optional[str] = Field(None, max_length=100)


class WalletUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    currency: str
    available_balance: Decimal
    pending_balance: Decimal
    status: WalletStatus
    name: Optional[str]
    created_at: datetime
    updated_at: datetime


class WalletFreezeRequest(BaseModel):
    reason: Optional[str] = None
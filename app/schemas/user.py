from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    phone: Optional[str] = None
    role: UserRole = UserRole.CUSTOMER


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
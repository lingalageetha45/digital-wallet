from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    type: Optional[str] = None
    exp: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    is_active: bool
    is_verified: bool
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None
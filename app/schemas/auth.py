from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """
    Public patient registration request.

    Public registration intentionally does not accept a role.
    New public accounts are always created as patients.
    """

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class LoginRequest(BaseModel):
    """
    Login credentials.
    """

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class TokenResponse(BaseModel):
    """
    JWT access token returned after successful authentication.
    """

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """
    Safe user representation.

    The password hash is intentionally excluded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

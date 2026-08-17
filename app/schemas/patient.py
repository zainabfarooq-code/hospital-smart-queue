from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    address: str | None = None
    emergency_contact: str | None = Field(default=None, max_length=150)


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    address: str | None = None
    emergency_contact: str | None = Field(default=None, max_length=150)


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    full_name: str
    phone: str | None
    date_of_birth: date | None
    gender: str | None
    address: str | None
    emergency_contact: str | None
    created_at: datetime
    updated_at: datetime

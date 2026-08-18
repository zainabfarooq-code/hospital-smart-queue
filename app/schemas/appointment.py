from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    doctor_id: UUID
    department_id: UUID
    appointment_date: date
    appointment_time: time
    reason: str | None = Field(default=None, max_length=1000)


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    doctor_id: UUID
    department_id: UUID
    appointment_date: date
    appointment_time: time
    status: str
    reason: str | None
    booked_at: datetime
    checked_in_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None

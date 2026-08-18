from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class QueueCreate(BaseModel):
    appointment_id: UUID


class QueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_id: UUID
    doctor_id: UUID
    queue_date: date
    token_number: int
    status: str
    check_in_time: datetime
    called_at: datetime | None
    service_started_at: datetime | None
    completed_at: datetime | None
    skipped_at: datetime | None
    cancelled_at: datetime | None

    predicted_wait_minutes: float | None = None
    patients_ahead: int = 0

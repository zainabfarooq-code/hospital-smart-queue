from datetime import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DoctorScheduleCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(default=15, ge=5, le=240)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_time >= self.end_time:
            raise ValueError(
                "start_time must be earlier than end_time."
            )
        return self


class DoctorScheduleUpdate(BaseModel):
    day_of_week: int | None = Field(
        default=None,
        ge=0,
        le=6,
    )
    start_time: time | None = None
    end_time: time | None = None
    slot_duration_minutes: int | None = Field(
        default=None,
        ge=5,
        le=240,
    )
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValueError(
                "start_time must be earlier than end_time."
            )
        return self


class DoctorScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_minutes: int
    is_active: bool

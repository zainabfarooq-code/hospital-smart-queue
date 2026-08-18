import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    queue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queues.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    queue_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    patients_ahead: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    appointment_hour: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    consultation_duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    arrival_delay_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    predicted_wait_minutes: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    actual_wait_minutes: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

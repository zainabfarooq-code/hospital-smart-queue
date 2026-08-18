from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import (
    RequireDoctor,
    RequirePatient,
)
from app.db.database import get_db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.queue import Queue
from app.models.queue_event import QueueEvent
from app.models.prediction import Prediction
from app.schemas.queue import QueueCreate, QueueResponse
from app.services.prediction_service import prediction_service


router = APIRouter(
    prefix="/queues",
    tags=["Queues"],
)


def _get_patient(
    current_user,
    db: Session,
) -> Patient:
    patient = db.execute(
        select(Patient).where(
            Patient.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    return patient


def _get_queue(
    queue_id: UUID,
    db: Session,
) -> Queue:
    queue = db.execute(
        select(Queue).where(
            Queue.id == queue_id
        )
    ).scalar_one_or_none()

    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue entry not found.",
        )

    return queue


def _create_event(
    db: Session,
    queue: Queue,
    event_type: str,
    performed_by: UUID | None = None,
    notes: str | None = None,
) -> None:
    event = QueueEvent(
        queue_id=queue.id,
        event_type=event_type,
        performed_by=performed_by,
        notes=notes,
    )

    db.add(event)


@router.post(
    "/check-in",
    response_model=QueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def check_in_to_queue(
    request: QueueCreate,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Queue:

    patient = _get_patient(
        current_user,
        db,
    )

    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == request.appointment_id
        )
    ).scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found.",
        )

    if appointment.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only check in to your own appointment.",
        )

    if appointment.status != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only scheduled appointments can be checked in.",
        )

    existing_queue = db.execute(
        select(Queue).where(
            Queue.appointment_id == appointment.id
        )
    ).scalar_one_or_none()

    if existing_queue is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This appointment is already in the queue.",
        )

    queue_date = appointment.appointment_date

    last_token = db.execute(
        select(func.max(Queue.token_number)).where(
            Queue.doctor_id == appointment.doctor_id,
            Queue.queue_date == queue_date,
        )
    ).scalar_one()

    token_number = (last_token or 0) + 1

    queue_length = db.execute(
        select(func.count(Queue.id)).where(
            Queue.doctor_id == appointment.doctor_id,
            Queue.queue_date == queue_date,
            Queue.status.in_(
                ["waiting", "called", "in_progress"]
            ),
        )
    ).scalar_one() or 0

    patients_ahead = db.execute(
        select(func.count(Queue.id)).where(
            Queue.doctor_id == appointment.doctor_id,
            Queue.queue_date == queue_date,
            Queue.token_number < token_number,
            Queue.status.in_(
                ["waiting", "called", "in_progress"]
            ),
        )
    ).scalar_one() or 0

    doctor = db.execute(
        select(Doctor).where(
            Doctor.id == appointment.doctor_id
        )
    ).scalar_one_or_none()

    consultation_duration_minutes = (
        doctor.consultation_duration_minutes
        if doctor is not None
        else 15
    )

    appointment_time = getattr(
        appointment,
        "appointment_time",
        None,
    )

    appointment_hour = (
        appointment_time.hour
        if appointment_time is not None
        else 0
    )

    now = datetime.now(timezone.utc)

    if appointment_time is None:
        arrival_delay_minutes = 0
    else:
        appointment_datetime = datetime.combine(
            appointment.appointment_date,
            appointment_time,
        )

        if appointment_datetime.tzinfo is None:
            arrival_delay_minutes = max(
                0,
                int(
                    (
                        now.replace(tzinfo=None)
                        - appointment_datetime
                    ).total_seconds()
                    / 60
                ),
            )
        else:
            arrival_delay_minutes = max(
                0,
                int(
                    (
                        now
                        - appointment_datetime
                    ).total_seconds()
                    / 60
                ),
            )

    predicted_wait_minutes = prediction_service.predict(
        queue_length=int(queue_length),
        patients_ahead=int(patients_ahead),
        appointment_hour=appointment_hour,
        day_of_week=appointment.appointment_date.weekday(),
        consultation_duration_minutes=(
            consultation_duration_minutes
        ),
        arrival_delay_minutes=arrival_delay_minutes,
    )

    queue = Queue(
        appointment_id=appointment.id,
        doctor_id=appointment.doctor_id,
        queue_date=queue_date,
        token_number=token_number,
        status="waiting",
    )

    db.add(queue)

    appointment.status = "checked_in"
    appointment.checked_in_at = now

    try:
        db.flush()

        prediction = Prediction(
            appointment_id=appointment.id,
            queue_id=queue.id,
            queue_length=int(queue_length),
            patients_ahead=int(patients_ahead),
            appointment_hour=appointment_hour,
            day_of_week=appointment.appointment_date.weekday(),
            consultation_duration_minutes=(
                consultation_duration_minutes
            ),
            arrival_delay_minutes=arrival_delay_minutes,
            predicted_wait_minutes=predicted_wait_minutes,
            model_version=prediction_service.model_version,
        )

        db.add(prediction)

        _create_event(
            db=db,
            queue=queue,
            event_type="checked_in",
            performed_by=current_user.id,
        )

        db.commit()
        db.refresh(queue)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not check in to the queue.",
        )

    queue.predicted_wait_minutes = predicted_wait_minutes
    queue.patients_ahead = int(patients_ahead)

    return queue


@router.get(
    "/me",
    response_model=list[QueueResponse],
)
def get_my_queue_entries(
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> list[Queue]:

    patient = _get_patient(
        current_user,
        db,
    )

    queues = db.execute(
        select(Queue)
        .join(
            Appointment,
            Appointment.id == Queue.appointment_id,
        )
        .where(
            Appointment.patient_id == patient.id
        )
        .order_by(
            Queue.queue_date.desc(),
            Queue.token_number,
        )
    ).scalars().all()

    return list(queues)


@router.get(
    "/doctor",
    response_model=list[QueueResponse],
)
def get_doctor_queue(
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> list[Queue]:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    today = datetime.now(timezone.utc).date()

    queues = db.execute(
        select(Queue)
        .where(
            Queue.doctor_id == doctor.id,
            Queue.queue_date == today,
        )
        .order_by(
            Queue.token_number,
        )
    ).scalars().all()

    return list(queues)


@router.post(
    "/{queue_id}/call",
    response_model=QueueResponse,
)
def call_queue_patient(
    queue_id: UUID,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> Queue:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    queue = _get_queue(
        queue_id,
        db,
    )

    if queue.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own queue.",
        )

    if queue.status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only waiting patients can be called.",
        )

    queue.status = "called"
    queue.called_at = datetime.now(timezone.utc)

    _create_event(
        db=db,
        queue=queue,
        event_type="called",
        performed_by=current_user.id,
    )

    db.commit()
    db.refresh(queue)

    return queue


@router.post(
    "/{queue_id}/start",
    response_model=QueueResponse,
)
def start_queue_service(
    queue_id: UUID,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> Queue:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    queue = _get_queue(
        queue_id,
        db,
    )

    if queue.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own queue.",
        )

    if queue.status != "called":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only called patients can start service.",
        )

    queue.status = "in_progress"
    queue.service_started_at = datetime.now(timezone.utc)

    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == queue.appointment_id
        )
    ).scalar_one_or_none()

    if appointment is not None:
        appointment.status = "in_progress"

    _create_event(
        db=db,
        queue=queue,
        event_type="service_started",
        performed_by=current_user.id,
    )

    db.commit()
    db.refresh(queue)

    return queue


@router.post(
    "/{queue_id}/complete",
    response_model=QueueResponse,
)
def complete_queue_service(
    queue_id: UUID,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> Queue:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    queue = _get_queue(
        queue_id,
        db,
    )

    if queue.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own queue.",
        )

    if queue.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only patients currently in service can be completed.",
        )

    now = datetime.now(timezone.utc)

    queue.status = "completed"
    queue.completed_at = now

    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == queue.appointment_id
        )
    ).scalar_one_or_none()

    if appointment is not None:
        appointment.status = "completed"
        appointment.completed_at = now

    _create_event(
        db=db,
        queue=queue,
        event_type="service_completed",
        performed_by=current_user.id,
    )

    db.commit()
    db.refresh(queue)

    return queue


@router.post(
    "/{queue_id}/skip",
    response_model=QueueResponse,
)
def skip_queue_patient(
    queue_id: UUID,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> Queue:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.user_id == current_user.id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    queue = _get_queue(
        queue_id,
        db,
    )

    if queue.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own queue.",
        )

    if queue.status not in {"waiting", "called"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only waiting or called patients can be skipped.",
        )

    queue.status = "skipped"
    queue.skipped_at = datetime.now(timezone.utc)

    _create_event(
        db=db,
        queue=queue,
        event_type="skipped",
        performed_by=current_user.id,
    )

    db.commit()
    db.refresh(queue)

    return queue


@router.post(
    "/{queue_id}/cancel",
    response_model=QueueResponse,
)
def cancel_queue_entry(
    queue_id: UUID,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Queue:

    patient = _get_patient(
        current_user,
        db,
    )

    queue = _get_queue(
        queue_id,
        db,
    )

    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == queue.appointment_id
        )
    ).scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found.",
        )

    if appointment.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own queue entry.",
        )

    if queue.status not in {"waiting", "called"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This queue entry cannot be cancelled.",
        )

    now = datetime.now(timezone.utc)

    queue.status = "cancelled"
    queue.cancelled_at = now

    if appointment.status == "checked_in":
        appointment.status = "cancelled"
        appointment.cancelled_at = now

    _create_event(
        db=db,
        queue=queue,
        event_type="cancelled",
        performed_by=current_user.id,
    )

    db.commit()
    db.refresh(queue)

    return queue

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import (
    RequireAdmin,
    RequireDoctor,
    RequireDoctorOrAdmin,
    RequirePatient,
)
from app.db.database import get_db
from app.models.appointment import Appointment
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.schemas.appointment import AppointmentCreate, AppointmentResponse


router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
)


@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    request: AppointmentCreate,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Appointment:

    patient = db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    doctor = db.execute(
        select(Doctor).where(Doctor.id == request.doctor_id)
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found.",
        )

    if not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor is not active.",
        )

    department = db.execute(
        select(Department).where(
            Department.id == request.department_id
        )
    ).scalar_one_or_none()

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )

    if not department.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is not active.",
        )

    if doctor.department_id != request.department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor does not belong to the selected department.",
        )

    appointment_datetime = datetime.combine(
        request.appointment_date,
        request.appointment_time,
    )

    if appointment_datetime <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment must be scheduled for a future date and time.",
        )

    existing_appointment = db.execute(
        select(Appointment).where(
            Appointment.doctor_id == request.doctor_id,
            Appointment.appointment_date == request.appointment_date,
            Appointment.appointment_time == request.appointment_time,
            Appointment.status == "scheduled",
        )
    ).scalar_one_or_none()

    if existing_appointment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This appointment slot is already booked.",
        )

    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=request.doctor_id,
        department_id=request.department_id,
        appointment_date=request.appointment_date,
        appointment_time=request.appointment_time,
        reason=request.reason,
    )

    db.add(appointment)

    try:
        db.commit()
        db.refresh(appointment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment could not be created.",
        )

    return appointment


@router.get(
    "/me",
    response_model=list[AppointmentResponse],
)
def get_my_appointments(
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> list[Appointment]:

    patient = db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    appointments = db.execute(
        select(Appointment)
        .where(Appointment.patient_id == patient.id)
        .order_by(
            Appointment.appointment_date,
            Appointment.appointment_time,
        )
    ).scalars().all()

    return list(appointments)


@router.get(
    "/doctor",
    response_model=list[AppointmentResponse],
)
def get_doctor_appointments(
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> list[Appointment]:

    doctor = db.execute(
        select(Doctor).where(Doctor.user_id == current_user.id)
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found.",
        )

    appointments = db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor.id)
        .order_by(
            Appointment.appointment_date,
            Appointment.appointment_time,
        )
    ).scalars().all()

    return list(appointments)


def _get_appointment(
    appointment_id: UUID,
    db: Session,
) -> Appointment:

    appointment = db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id
        )
    ).scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found.",
        )

    return appointment


def _validate_status_transition(
    current_status: str,
    new_status: str,
) -> None:

    allowed_transitions = {
        "scheduled": {"checked_in", "cancelled"},
        "checked_in": {"in_progress", "cancelled"},
        "in_progress": {"completed"},
        "completed": set(),
        "cancelled": set(),
    }

    if new_status not in allowed_transitions.get(
        current_status,
        set(),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid appointment status transition: "
                f"{current_status} -> {new_status}."
            ),
        )


@router.patch(
    "/{appointment_id}/status",
    response_model=AppointmentResponse,
)
def update_appointment_status(
    appointment_id: UUID,
    new_status: str,
    current_user: RequireDoctorOrAdmin,
    db: Session = Depends(get_db),
) -> Appointment:

    allowed_statuses = {
        "scheduled",
        "checked_in",
        "in_progress",
        "completed",
        "cancelled",
    }

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid appointment status.",
        )

    appointment = _get_appointment(
        appointment_id,
        db,
    )

    if current_user.role == "doctor":
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

        if appointment.doctor_id != doctor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage your own appointments.",
            )

    _validate_status_transition(
        appointment.status,
        new_status,
    )

    appointment.status = new_status

    now = datetime.now(timezone.utc)

    if new_status == "checked_in":
        appointment.checked_in_at = now

    elif new_status == "completed":
        appointment.completed_at = now

    elif new_status == "cancelled":
        appointment.cancelled_at = now

    db.commit()
    db.refresh(appointment)

    return appointment


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
)
def cancel_appointment(
    appointment_id: UUID,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Appointment:

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

    appointment = _get_appointment(
        appointment_id,
        db,
    )

    if appointment.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own appointments.",
        )

    if appointment.status != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only scheduled appointments can be cancelled.",
        )

    appointment.status = "cancelled"
    appointment.cancelled_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(appointment)

    return appointment

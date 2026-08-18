from datetime import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import RequireAdmin, RequireDoctor
from app.db.database import get_db
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.schemas.doctor_schedule import (
    DoctorScheduleCreate,
    DoctorScheduleResponse,
    DoctorScheduleUpdate,
)

router = APIRouter(
    prefix="/doctor-schedules",
    tags=["Doctor Schedules"],
)


def _get_doctor_for_user(
    current_user,
    db: Session,
) -> Doctor:
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

    return doctor


def _validate_no_overlap(
    doctor_id: UUID,
    day_of_week: int,
    start_time: time,
    end_time: time,
    db: Session,
    exclude_id: UUID | None = None,
) -> None:
    query = select(DoctorSchedule).where(
        DoctorSchedule.doctor_id == doctor_id,
        DoctorSchedule.day_of_week == day_of_week,
        DoctorSchedule.is_active.is_(True),
        DoctorSchedule.start_time < end_time,
        DoctorSchedule.end_time > start_time,
    )

    if exclude_id is not None:
        query = query.where(
            DoctorSchedule.id != exclude_id
        )

    existing = db.execute(query).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has an overlapping schedule.",
        )


@router.post(
    "",
    response_model=DoctorScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_doctor_schedule(
    request: DoctorScheduleCreate,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> DoctorSchedule:

    doctor = _get_doctor_for_user(
        current_user,
        db,
    )

    if not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor is not active.",
        )

    if request.is_active:
        _validate_no_overlap(
            doctor.id,
            request.day_of_week,
            request.start_time,
            request.end_time,
            db,
        )

    schedule = DoctorSchedule(
        doctor_id=doctor.id,
        day_of_week=request.day_of_week,
        start_time=request.start_time,
        end_time=request.end_time,
        slot_duration_minutes=request.slot_duration_minutes,
        is_active=request.is_active,
    )

    db.add(schedule)

    try:
        db.commit()
        db.refresh(schedule)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor schedule could not be created.",
        )

    return schedule


@router.get(
    "/me",
    response_model=list[DoctorScheduleResponse],
)
def get_my_doctor_schedules(
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> list[DoctorSchedule]:

    doctor = _get_doctor_for_user(
        current_user,
        db,
    )

    schedules = db.execute(
        select(DoctorSchedule)
        .where(
            DoctorSchedule.doctor_id == doctor.id
        )
        .order_by(
            DoctorSchedule.day_of_week,
            DoctorSchedule.start_time,
        )
    ).scalars().all()

    return list(schedules)


@router.get(
    "/doctor/{doctor_id}",
    response_model=list[DoctorScheduleResponse],
)
def get_doctor_schedules(
    doctor_id: UUID,
    db: Session = Depends(get_db),
) -> list[DoctorSchedule]:

    doctor = db.execute(
        select(Doctor).where(
            Doctor.id == doctor_id
        )
    ).scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found.",
        )

    schedules = db.execute(
        select(DoctorSchedule)
        .where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.is_active.is_(True),
        )
        .order_by(
            DoctorSchedule.day_of_week,
            DoctorSchedule.start_time,
        )
    ).scalars().all()

    return list(schedules)


@router.put(
    "/{schedule_id}",
    response_model=DoctorScheduleResponse,
)
def update_doctor_schedule(
    schedule_id: UUID,
    request: DoctorScheduleUpdate,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> DoctorSchedule:

    doctor = _get_doctor_for_user(
        current_user,
        db,
    )

    schedule = db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.id == schedule_id
        )
    ).scalar_one_or_none()

    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor schedule not found.",
        )

    if schedule.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your own schedules.",
        )

    update_data = request.model_dump(
        exclude_unset=True
    )

    new_day = update_data.get(
        "day_of_week",
        schedule.day_of_week,
    )

    new_start = update_data.get(
        "start_time",
        schedule.start_time,
    )

    new_end = update_data.get(
        "end_time",
        schedule.end_time,
    )

    new_active = update_data.get(
        "is_active",
        schedule.is_active,
    )

    if new_start >= new_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be earlier than end_time.",
        )

    if new_active:
        _validate_no_overlap(
            doctor.id,
            new_day,
            new_start,
            new_end,
            db,
            exclude_id=schedule.id,
        )

    for field, value in update_data.items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)

    return schedule


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_doctor_schedule(
    schedule_id: UUID,
    current_user: RequireDoctor,
    db: Session = Depends(get_db),
) -> None:

    doctor = _get_doctor_for_user(
        current_user,
        db,
    )

    schedule = db.execute(
        select(DoctorSchedule).where(
            DoctorSchedule.id == schedule_id
        )
    ).scalar_one_or_none()

    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor schedule not found.",
        )

    if schedule.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own schedules.",
        )

    db.delete(schedule)
    db.commit()

    return None

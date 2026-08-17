from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import RequirePatient
from app.db.database import get_db
from app.models.patient import Patient
from app.schemas.patient import (
    PatientCreate,
    PatientResponse,
    PatientUpdate,
)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
)


@router.post(
    "/profile",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_profile(
    request: PatientCreate,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Patient:
    existing_profile = db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    ).scalar_one_or_none()

    if existing_profile is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient profile already exists.",
        )

    patient = Patient(
        user_id=current_user.id,
        full_name=request.full_name.strip(),
        phone=request.phone,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        address=request.address,
        emergency_contact=request.emergency_contact,
    )

    db.add(patient)

    try:
        db.commit()
        db.refresh(patient)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient profile could not be created.",
        )

    return patient


@router.get(
    "/me",
    response_model=PatientResponse,
)
def get_my_patient_profile(
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    return patient


@router.put(
    "/me",
    response_model=PatientResponse,
)
def update_my_patient_profile(
    request: PatientUpdate,
    current_user: RequirePatient,
    db: Session = Depends(get_db),
) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.user_id == current_user.id)
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient profile not found.",
        )

    update_data = request.model_dump(exclude_unset=True)

    if "full_name" in update_data and update_data["full_name"] is not None:
        update_data["full_name"] = update_data["full_name"].strip()

    for field, value in update_data.items():
        setattr(patient, field, value)

    db.commit()
    db.refresh(patient)

    return patient

from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.appointments import create_appointment
from app.schemas.appointment import AppointmentCreate


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, results):
        self.results = iter(results)
        self.added = None
        self.committed = False
        self.refreshed = False
        self.rolled_back = False

    def execute(self, statement):
        return FakeResult(next(self.results))

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True

    def rollback(self):
        self.rolled_back = True


def make_user():
    return SimpleNamespace(
        id=uuid4(),
        role="patient",
        is_active=True,
    )


def make_patient(user_id):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
    )


def make_doctor(department_id, active=True):
    return SimpleNamespace(
        id=uuid4(),
        department_id=department_id,
        is_active=active,
    )


def make_department(active=True):
    return SimpleNamespace(
        id=uuid4(),
        is_active=active,
    )


def make_request(doctor_id, department_id):
    return AppointmentCreate(
        doctor_id=doctor_id,
        department_id=department_id,
        appointment_date=date(2099, 1, 10),
        appointment_time=time(10, 0),
        reason="General consultation",
    )


def test_booking_requires_patient_profile():
    user = make_user()
    department = make_department()
    doctor = make_doctor(department.id)

    db = FakeDB([
        None,
        doctor,
        department,
    ])

    with pytest.raises(HTTPException) as exc:
        create_appointment(
            request=make_request(doctor.id, department.id),
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Patient profile not found."


def test_successful_booking():
    user = make_user()
    patient = make_patient(user.id)
    department = make_department()
    doctor = make_doctor(department.id)

    db = FakeDB([
        patient,
        doctor,
        department,
        None,
    ])

    result = create_appointment(
        request=make_request(doctor.id, department.id),
        current_user=user,
        db=db,
    )

    assert result is db.added
    assert result.patient_id == patient.id
    assert result.doctor_id == doctor.id
    assert result.department_id == department.id
    assert result.reason == "General consultation"
    assert db.committed is True
    assert db.refreshed is True


def test_duplicate_slot_is_rejected():
    user = make_user()
    patient = make_patient(user.id)
    department = make_department()
    doctor = make_doctor(department.id)
    existing = SimpleNamespace(id=uuid4())

    db = FakeDB([
        patient,
        doctor,
        department,
        existing,
    ])

    with pytest.raises(HTTPException) as exc:
        create_appointment(
            request=make_request(doctor.id, department.id),
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "This appointment slot is already booked."


def test_inactive_doctor_is_rejected():
    user = make_user()
    patient = make_patient(user.id)
    department = make_department()
    doctor = make_doctor(department.id, active=False)

    db = FakeDB([
        patient,
        doctor,
    ])

    with pytest.raises(HTTPException) as exc:
        create_appointment(
            request=make_request(doctor.id, department.id),
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Doctor is not active."


def test_department_mismatch_is_rejected():
    user = make_user()
    patient = make_patient(user.id)
    department = make_department()
    doctor_department = make_department()
    doctor = make_doctor(doctor_department.id)

    db = FakeDB([
        patient,
        doctor,
        department,
    ])

    with pytest.raises(HTTPException) as exc:
        create_appointment(
            request=make_request(doctor.id, department.id),
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == (
        "Doctor does not belong to the selected department."
    )

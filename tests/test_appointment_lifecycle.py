from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.appointments import (
    _validate_status_transition,
    cancel_appointment,
    update_appointment_status,
)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, results):
        self.results = iter(results)
        self.committed = False
        self.refreshed = False

    def execute(self, statement):
        return FakeResult(next(self.results))

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True


def make_user(role):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        is_active=True,
    )


def make_appointment(
    patient_id,
    doctor_id,
    appointment_id=None,
    status="scheduled",
):
    return SimpleNamespace(
        id=appointment_id or uuid4(),
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=status,
        checked_in_at=None,
        completed_at=None,
        cancelled_at=None,
    )


def test_valid_status_transitions():
    _validate_status_transition("scheduled", "checked_in")
    _validate_status_transition("checked_in", "in_progress")
    _validate_status_transition("in_progress", "completed")
    _validate_status_transition("scheduled", "cancelled")


def test_invalid_status_transition_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_status_transition("completed", "scheduled")

    assert exc.value.status_code == 400


def test_patient_can_cancel_own_scheduled_appointment():
    user = make_user("patient")
    patient = SimpleNamespace(id=uuid4(), user_id=user.id)
    appointment = make_appointment(patient.id, uuid4())

    db = FakeDB([
        patient,
        appointment,
    ])

    result = cancel_appointment(
        appointment_id=appointment.id,
        current_user=user,
        db=db,
    )

    assert result is appointment
    assert appointment.status == "cancelled"
    assert appointment.cancelled_at is not None
    assert db.committed is True
    assert db.refreshed is True


def test_patient_cannot_cancel_someone_elses_appointment():
    user = make_user("patient")
    patient = SimpleNamespace(id=uuid4(), user_id=user.id)
    appointment = make_appointment(uuid4(), uuid4())

    db = FakeDB([
        patient,
        appointment,
    ])

    with pytest.raises(HTTPException) as exc:
        cancel_appointment(
            appointment_id=appointment.id,
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 403


def test_cancelled_appointment_cannot_be_cancelled_again():
    user = make_user("patient")
    patient = SimpleNamespace(id=uuid4(), user_id=user.id)
    appointment = make_appointment(
        patient.id,
        uuid4(),
        status="cancelled",
    )

    db = FakeDB([
        patient,
        appointment,
    ])

    with pytest.raises(HTTPException) as exc:
        cancel_appointment(
            appointment_id=appointment.id,
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 400


def test_doctor_can_update_own_appointment():
    user = make_user("doctor")
    doctor = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
    )
    appointment = make_appointment(
        uuid4(),
        doctor.id,
        status="scheduled",
    )

    db = FakeDB([
        appointment,
        doctor,
    ])

    result = update_appointment_status(
        appointment_id=appointment.id,
        new_status="checked_in",
        current_user=user,
        db=db,
    )

    assert result is appointment
    assert appointment.status == "checked_in"
    assert appointment.checked_in_at is not None
    assert db.committed is True
    assert db.refreshed is True


def test_doctor_cannot_update_another_doctors_appointment():
    user = make_user("doctor")
    doctor = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
    )
    appointment = make_appointment(
        uuid4(),
        uuid4(),
        status="scheduled",
    )

    db = FakeDB([
        appointment,
        doctor,
    ])

    with pytest.raises(HTTPException) as exc:
        update_appointment_status(
            appointment_id=appointment.id,
            new_status="checked_in",
            current_user=user,
            db=db,
        )

    assert exc.value.status_code == 403


def test_doctor_can_complete_appointment_through_valid_flow():
    user = make_user("doctor")
    doctor = SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
    )
    appointment = make_appointment(
        uuid4(),
        doctor.id,
        status="in_progress",
    )

    db = FakeDB([
        appointment,
        doctor,
    ])

    result = update_appointment_status(
        appointment_id=appointment.id,
        new_status="completed",
        current_user=user,
        db=db,
    )

    assert result is appointment
    assert appointment.status == "completed"
    assert appointment.completed_at is not None

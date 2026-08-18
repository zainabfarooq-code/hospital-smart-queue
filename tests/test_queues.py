from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.queues import (
    call_queue_patient,
    cancel_queue_entry,
    check_in_to_queue,
    complete_queue_service,
    get_doctor_queue,
    get_my_queue_entries,
    skip_queue_patient,
    start_queue_service,
)
from app.schemas.queue import QueueCreate


class FakeResult:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = False
        self.refreshed = False
        self.flushed = False

    def execute(self, statement):
        if not self.results:
            return FakeResult(None)

        result = self.results.pop(0)

        if isinstance(result, list):
            return FakeResult(values=result)

        return FakeResult(result)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True

        for obj in self.added:
            if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True

    def rollback(self):
        pass


def make_user(role="patient"):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        is_active=True,
    )


def make_patient(user_id):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
    )


def make_doctor(user_id):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        is_active=True,
    )


def make_appointment(
    patient_id,
    doctor_id,
    status="scheduled",
):
    return SimpleNamespace(
        id=uuid4(),
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=date.today(),
        status=status,
        checked_in_at=None,
        completed_at=None,
        cancelled_at=None,
    )


def make_queue(
    appointment_id,
    doctor_id,
    status="waiting",
):
    return SimpleNamespace(
        id=uuid4(),
        appointment_id=appointment_id,
        doctor_id=doctor_id,
        queue_date=date.today(),
        token_number=1,
        status=status,
        check_in_time=datetime.now(timezone.utc),
        called_at=None,
        service_started_at=None,
        completed_at=None,
        skipped_at=None,
        cancelled_at=None,
    )


def test_check_in_success():
    user = make_user()
    patient = make_patient(user.id)
    doctor = make_doctor(uuid4())
    appointment = make_appointment(
        patient.id,
        doctor.id,
    )

    db = FakeDB([
        patient,
        appointment,
        None,
        0,
    ])

    result = check_in_to_queue(
        request=QueueCreate(
            appointment_id=appointment.id,
        ),
        current_user=user,
        db=db,
    )

    assert result.appointment_id == appointment.id
    assert result.doctor_id == doctor.id
    assert result.token_number == 1
    assert result.status == "waiting"
    assert appointment.status == "checked_in"
    assert db.committed is True
    assert db.refreshed is True


def test_check_in_rejects_missing_patient_profile():
    user = make_user()

    db = FakeDB([
        None,
    ])

    appointment_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        check_in_to_queue(
            request=QueueCreate(
                appointment_id=appointment_id,
            ),
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Patient profile not found."


def test_check_in_rejects_duplicate_queue():
    user = make_user()
    patient = make_patient(user.id)
    doctor = make_doctor(uuid4())
    appointment = make_appointment(
        patient.id,
        doctor.id,
    )
    existing_queue = make_queue(
        appointment.id,
        doctor.id,
    )

    db = FakeDB([
        patient,
        appointment,
        existing_queue,
    ])

    with pytest.raises(HTTPException) as exc_info:
        check_in_to_queue(
            request=QueueCreate(
                appointment_id=appointment.id,
            ),
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 409


def test_call_queue_patient_success():
    user = make_user("doctor")
    doctor = make_doctor(user.id)
    queue = make_queue(
        uuid4(),
        doctor.id,
    )

    db = FakeDB([
        doctor,
        queue,
    ])

    result = call_queue_patient(
        queue_id=queue.id,
        current_user=user,
        db=db,
    )

    assert result.status == "called"
    assert result.called_at is not None
    assert db.committed is True


def test_start_queue_service_success():
    user = make_user("doctor")
    doctor = make_doctor(user.id)
    queue = make_queue(
        uuid4(),
        doctor.id,
        status="called",
    )

    appointment = make_appointment(
        uuid4(),
        doctor.id,
        status="checked_in",
    )
    appointment.id = queue.appointment_id

    db = FakeDB([
        doctor,
        queue,
        appointment,
    ])

    result = start_queue_service(
        queue_id=queue.id,
        current_user=user,
        db=db,
    )

    assert result.status == "in_progress"
    assert result.service_started_at is not None
    assert appointment.status == "in_progress"
    assert db.committed is True


def test_complete_queue_service_success():
    user = make_user("doctor")
    doctor = make_doctor(user.id)
    queue = make_queue(
        uuid4(),
        doctor.id,
        status="in_progress",
    )

    appointment = make_appointment(
        uuid4(),
        doctor.id,
        status="in_progress",
    )
    appointment.id = queue.appointment_id

    db = FakeDB([
        doctor,
        queue,
        appointment,
    ])

    result = complete_queue_service(
        queue_id=queue.id,
        current_user=user,
        db=db,
    )

    assert result.status == "completed"
    assert result.completed_at is not None
    assert appointment.status == "completed"
    assert appointment.completed_at is not None


def test_skip_queue_patient_success():
    user = make_user("doctor")
    doctor = make_doctor(user.id)
    queue = make_queue(
        uuid4(),
        doctor.id,
        status="waiting",
    )

    db = FakeDB([
        doctor,
        queue,
    ])

    result = skip_queue_patient(
        queue_id=queue.id,
        current_user=user,
        db=db,
    )

    assert result.status == "skipped"
    assert result.skipped_at is not None


def test_patient_can_cancel_queue():
    user = make_user("patient")
    patient = make_patient(user.id)
    doctor = make_doctor(uuid4())

    queue = make_queue(
        uuid4(),
        doctor.id,
        status="waiting",
    )

    appointment = make_appointment(
        patient.id,
        doctor.id,
        status="checked_in",
    )
    appointment.id = queue.appointment_id

    db = FakeDB([
        patient,
        queue,
        appointment,
    ])

    result = cancel_queue_entry(
        queue_id=queue.id,
        current_user=user,
        db=db,
    )

    assert result.status == "cancelled"
    assert result.cancelled_at is not None
    assert appointment.status == "cancelled"


def test_patient_cannot_cancel_another_patient_queue():
    user = make_user("patient")
    patient = make_patient(user.id)
    other_patient = make_patient(uuid4())
    doctor = make_doctor(uuid4())

    queue = make_queue(
        uuid4(),
        doctor.id,
    )

    appointment = make_appointment(
        other_patient.id,
        doctor.id,
    )
    appointment.id = queue.appointment_id

    db = FakeDB([
        patient,
        queue,
        appointment,
    ])

    with pytest.raises(HTTPException) as exc_info:
        cancel_queue_entry(
            queue_id=queue.id,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 403


def test_doctor_cannot_manage_another_doctor_queue():
    user = make_user("doctor")
    doctor = make_doctor(user.id)
    other_doctor = make_doctor(uuid4())

    queue = make_queue(
        uuid4(),
        other_doctor.id,
    )

    db = FakeDB([
        doctor,
        queue,
    ])

    with pytest.raises(HTTPException) as exc_info:
        call_queue_patient(
            queue_id=queue.id,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 403

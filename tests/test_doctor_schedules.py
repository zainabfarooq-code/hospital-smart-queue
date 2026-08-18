from datetime import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.doctor_schedules import (
    create_doctor_schedule,
    delete_doctor_schedule,
    get_doctor_schedules,
    get_my_doctor_schedules,
    update_doctor_schedule,
)
from app.schemas.doctor_schedule import (
    DoctorScheduleCreate,
    DoctorScheduleUpdate,
)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        if self.value is None:
            return []
        return self.value


class FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = None
        self.deleted = None
        self.committed = False
        self.refreshed = False

    def execute(self, statement):
        value = self.results.pop(0) if self.results else None
        return FakeResult(value)

    def add(self, obj):
        self.added = obj

    def delete(self, obj):
        self.deleted = obj

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True

    def rollback(self):
        pass


def make_user(role="doctor"):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        is_active=True,
    )


def make_doctor(user):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user.id,
        department_id=uuid4(),
        full_name="Dr. Test",
        is_active=True,
    )


def make_schedule(doctor_id):
    return SimpleNamespace(
        id=uuid4(),
        doctor_id=doctor_id,
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(13, 0),
        slot_duration_minutes=15,
        is_active=True,
    )


def test_create_schedule_success():
    user = make_user()
    doctor = make_doctor(user)

    db = FakeDB([
        doctor,
        None,
    ])

    request = DoctorScheduleCreate(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(13, 0),
        slot_duration_minutes=15,
        is_active=True,
    )

    result = create_doctor_schedule(
        request=request,
        current_user=user,
        db=db,
    )

    assert result.doctor_id == doctor.id
    assert result.day_of_week == 0
    assert result.start_time == time(9, 0)
    assert result.end_time == time(13, 0)
    assert result.slot_duration_minutes == 15
    assert result.is_active is True
    assert db.added is result
    assert db.committed is True
    assert db.refreshed is True


def test_create_schedule_rejects_inactive_doctor():
    user = make_user()
    doctor = make_doctor(user)
    doctor.is_active = False

    db = FakeDB([doctor])

    request = DoctorScheduleCreate(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(13, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_doctor_schedule(
            request=request,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Doctor is not active."


def test_create_schedule_rejects_overlap():
    user = make_user()
    doctor = make_doctor(user)

    existing = make_schedule(doctor.id)

    db = FakeDB([
        doctor,
        existing,
    ])

    request = DoctorScheduleCreate(
        day_of_week=0,
        start_time=time(10, 0),
        end_time=time(14, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_doctor_schedule(
            request=request,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Doctor already has an overlapping schedule."
    )


def test_get_my_schedules():
    user = make_user()
    doctor = make_doctor(user)

    schedules = [
        make_schedule(doctor.id),
        make_schedule(doctor.id),
    ]

    db = FakeDB([
        doctor,
        schedules,
    ])

    result = get_my_doctor_schedules(
        current_user=user,
        db=db,
    )

    assert result == schedules


def test_get_my_schedules_requires_doctor_profile():
    user = make_user()

    db = FakeDB([None])

    with pytest.raises(HTTPException) as exc_info:
        get_my_doctor_schedules(
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Doctor profile not found."


def test_get_public_doctor_schedules():
    doctor = SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )

    schedules = [
        make_schedule(doctor.id),
    ]

    db = FakeDB([
        doctor,
        schedules,
    ])

    result = get_doctor_schedules(
        doctor_id=doctor.id,
        db=db,
    )

    assert result == schedules


def test_get_public_doctor_schedules_returns_404():
    doctor_id = uuid4()

    db = FakeDB([None])

    with pytest.raises(HTTPException) as exc_info:
        get_doctor_schedules(
            doctor_id=doctor_id,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Doctor not found."


def test_update_schedule_success():
    user = make_user()
    doctor = make_doctor(user)
    schedule = make_schedule(doctor.id)

    db = FakeDB([
        doctor,
        schedule,
        None,
    ])

    request = DoctorScheduleUpdate(
        start_time=time(10, 0),
        end_time=time(14, 0),
        slot_duration_minutes=30,
    )

    result = update_doctor_schedule(
        schedule_id=schedule.id,
        request=request,
        current_user=user,
        db=db,
    )

    assert result is schedule
    assert schedule.start_time == time(10, 0)
    assert schedule.end_time == time(14, 0)
    assert schedule.slot_duration_minutes == 30
    assert db.committed is True
    assert db.refreshed is True


def test_update_schedule_rejects_other_doctor():
    user = make_user()
    doctor = make_doctor(user)

    other_doctor_id = uuid4()

    schedule = make_schedule(other_doctor_id)

    db = FakeDB([
        doctor,
        schedule,
    ])

    request = DoctorScheduleUpdate(
        start_time=time(10, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        update_doctor_schedule(
            schedule_id=schedule.id,
            request=request,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "You can only manage your own schedules."
    )


def test_update_schedule_rejects_invalid_time_range():
    user = make_user()
    doctor = make_doctor(user)
    schedule = make_schedule(doctor.id)

    db = FakeDB([
        doctor,
        schedule,
    ])

    with pytest.raises(
        ValueError,
        match="start_time must be earlier than end_time",
    ):
        DoctorScheduleUpdate(
            start_time=time(14, 0),
            end_time=time(10, 0),
        )


def test_delete_schedule_success():
    user = make_user()
    doctor = make_doctor(user)
    schedule = make_schedule(doctor.id)

    db = FakeDB([
        doctor,
        schedule,
    ])

    result = delete_doctor_schedule(
        schedule_id=schedule.id,
        current_user=user,
        db=db,
    )

    assert result is None
    assert db.deleted is schedule
    assert db.committed is True


def test_delete_schedule_rejects_other_doctor():
    user = make_user()
    doctor = make_doctor(user)

    schedule = make_schedule(uuid4())

    db = FakeDB([
        doctor,
        schedule,
    ])

    with pytest.raises(HTTPException) as exc_info:
        delete_doctor_schedule(
            schedule_id=schedule.id,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "You can only delete your own schedules."
    )

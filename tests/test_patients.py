from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.patients import (
    create_patient_profile,
    get_my_patient_profile,
    update_my_patient_profile,
)
from app.schemas.patient import PatientCreate, PatientUpdate


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeExecute:
    def __init__(self, value):
        self.value = value

    def __call__(self, statement):
        return FakeResult(self.value)


class FakeDB:
    def __init__(self, query_result=None):
        self.query_result = query_result
        self.added = None
        self.committed = False
        self.refreshed = False

    def execute(self, statement):
        return FakeResult(self.query_result)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True

    def rollback(self):
        pass


def make_patient_user():
    return SimpleNamespace(
        id=uuid4(),
        role="patient",
        is_active=True,
    )


def test_create_patient_profile_success():
    user = make_patient_user()
    db = FakeDB()

    request = PatientCreate(
        full_name="Zainab Farooq",
        phone="03001234567",
        date_of_birth=date(2006, 4, 15),
        gender="female",
        address="Sialkot",
        emergency_contact="03009876543",
    )

    result = create_patient_profile(
        request=request,
        current_user=user,
        db=db,
    )

    assert result.user_id == user.id
    assert result.full_name == "Zainab Farooq"
    assert result.phone == "03001234567"
    assert result.date_of_birth == date(2006, 4, 15)
    assert result.gender == "female"
    assert db.added is result
    assert db.committed is True
    assert db.refreshed is True


def test_create_patient_profile_rejects_duplicate():
    user = make_patient_user()

    existing_patient = SimpleNamespace(
        user_id=user.id,
        full_name="Existing Patient",
    )

    db = FakeDB(query_result=existing_patient)

    request = PatientCreate(
        full_name="New Patient",
    )

    with pytest.raises(HTTPException) as exc_info:
        create_patient_profile(
            request=request,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Patient profile already exists."


def test_get_patient_profile_success():
    user = make_patient_user()

    patient = SimpleNamespace(
        user_id=user.id,
        full_name="Zainab Farooq",
    )

    db = FakeDB(query_result=patient)

    result = get_my_patient_profile(
        current_user=user,
        db=db,
    )

    assert result is patient


def test_get_patient_profile_returns_404_when_missing():
    user = make_patient_user()
    db = FakeDB(query_result=None)

    with pytest.raises(HTTPException) as exc_info:
        get_my_patient_profile(
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Patient profile not found."


def test_update_patient_profile_success():
    user = make_patient_user()

    patient = SimpleNamespace(
        user_id=user.id,
        full_name="Old Name",
        phone="03000000000",
        address="Old Address",
    )

    db = FakeDB(query_result=patient)

    request = PatientUpdate(
        full_name="  New Name  ",
        phone="03111111111",
        address="New Address",
    )

    result = update_my_patient_profile(
        request=request,
        current_user=user,
        db=db,
    )

    assert result is patient
    assert patient.full_name == "New Name"
    assert patient.phone == "03111111111"
    assert patient.address == "New Address"
    assert db.committed is True
    assert db.refreshed is True


def test_update_patient_profile_returns_404_when_missing():
    user = make_patient_user()
    db = FakeDB(query_result=None)

    request = PatientUpdate(
        full_name="New Name",
    )

    with pytest.raises(HTTPException) as exc_info:
        update_my_patient_profile(
            request=request,
            current_user=user,
            db=db,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Patient profile not found."

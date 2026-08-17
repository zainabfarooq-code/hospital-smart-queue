from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.dependencies import require_role
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_is_hashed():
    password = "TestPassword123!"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$2")
    assert len(password_hash) == 60


def test_password_verification_succeeds_for_correct_password():
    password = "TestPassword123!"

    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_password_verification_fails_for_wrong_password():
    password_hash = hash_password("TestPassword123!")

    assert verify_password("WrongPassword123!", password_hash) is False


def test_create_and_decode_access_token():
    user_id = "12345678-1234-1234-1234-123456789012"

    token = create_access_token(
        subject=user_id,
        role="patient",
    )

    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["role"] == "patient"
    assert "exp" in payload


def test_invalid_token_returns_none():
    payload = decode_access_token("this-is-not-a-valid-jwt")

    assert payload is None


def test_patient_role_is_allowed_for_patient_dependency():
    user = SimpleNamespace(
        role="patient",
        is_active=True,
    )

    dependency = require_role("patient")

    result = dependency(user)

    assert result is user


def test_patient_role_is_rejected_by_doctor_dependency():
    user = SimpleNamespace(
        role="patient",
        is_active=True,
    )

    dependency = require_role("doctor")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == (
        "You do not have permission to access this resource."
    )


def test_patient_role_is_rejected_by_admin_dependency():
    user = SimpleNamespace(
        role="patient",
        is_active=True,
    )

    dependency = require_role("admin")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user)

    assert exc_info.value.status_code == 403


def test_doctor_role_is_allowed_for_doctor_dependency():
    user = SimpleNamespace(
        role="doctor",
        is_active=True,
    )

    dependency = require_role("doctor")

    result = dependency(user)

    assert result is user


def test_admin_role_is_allowed_for_admin_dependency():
    user = SimpleNamespace(
        role="admin",
        is_active=True,
    )

    dependency = require_role("admin")

    result = dependency(user)

    assert result is user


def test_doctor_role_is_rejected_by_patient_dependency():
    user = SimpleNamespace(
        role="doctor",
        is_active=True,
    )

    dependency = require_role("patient")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user)

    assert exc_info.value.status_code == 403


def test_admin_role_is_rejected_by_patient_dependency():
    user = SimpleNamespace(
        role="admin",
        is_active=True,
    )

    dependency = require_role("patient")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user)

    assert exc_info.value.status_code == 403

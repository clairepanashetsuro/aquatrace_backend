import pytest
from pydantic import ValidationError

from models.user import UserRole
from schemas.user import UserCreate, PasswordResetRequest


def test_user_creation_accepts_password_meeting_policy():
    payload = UserCreate(
        first_name="Aqua",
        last_name="Trace",
        email="Aqua.Trace@example.com",
        password="LongSecurePass1!",
        role=UserRole.FIELD_OFFICER,
    )
    assert payload.email == "aqua.trace@example.com"


def test_user_creation_rejects_password_without_special_character():
    with pytest.raises(ValidationError):
        UserCreate(
            first_name="Aqua",
            last_name="Trace",
            email="aqua@example.com",
            password="LongSecurePass123",
            role=UserRole.FIELD_OFFICER,
        )


def test_password_reset_uses_same_password_policy():
    with pytest.raises(ValidationError):
        PasswordResetRequest(new_password="password123456")

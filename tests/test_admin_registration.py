import pytest
from fastapi.testclient import TestClient

from core.security import verify_password
from main import app
from models.user import User, UserRole, UserStatus
from database import get_db


ADMIN_REGISTER_URL = "/admin/register"


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_payload():
    return {
        "first_name": "Test",
        "last_name": "Administrator",
        "email": "new.admin@example.com",
        "password": "SecurePassword123!",
    }


def test_admin_registration_creates_admin(client, db_session, admin_payload):
    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == admin_payload["email"]
    assert data["role"] == UserRole.ADMIN.value
    assert data["status"] == UserStatus.ACTIVE.value
    assert data["mfa_enabled"] is False
    assert "password_hash" not in data

    user = db_session.query(User).filter_by(email=admin_payload["email"]).first()

    assert user is not None
    assert user.role == UserRole.ADMIN
    assert user.status == UserStatus.ACTIVE
    assert user.password_hash != admin_payload["password"]
    assert verify_password(admin_payload["password"], user.password_hash)


def test_admin_registration_normalizes_email(client, db_session, admin_payload):
    admin_payload["email"] = "  NEW.ADMIN@EXAMPLE.COM  "

    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)

    assert response.status_code == 201
    assert response.json()["email"] == "new.admin@example.com"

    user = db_session.query(User).filter_by(email="new.admin@example.com").first()
    assert user is not None


def test_admin_registration_rejects_duplicate_email(client, db_session, admin_payload):
    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)
    assert response.status_code == 201

    duplicate_payload = {
        **admin_payload,
        "first_name": "Another",
        "last_name": "Administrator",
    }

    response = client.post(ADMIN_REGISTER_URL, json=duplicate_payload)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "password",
    [
        "short1!",
        "passwordwithoutspecial123",
        "PasswordWithoutNumber!",
        " ",
    ],
)
def test_admin_registration_rejects_weak_password(client, admin_payload, password):
    admin_payload["password"] = password

    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)

    assert response.status_code == 422


def test_admin_registration_requires_first_and_last_name(client, admin_payload):
    admin_payload.pop("first_name")

    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)

    assert response.status_code == 422


def test_admin_registration_rejects_unexpected_role(client, admin_payload):
    admin_payload["role"] = "Admin"

    response = client.post(ADMIN_REGISTER_URL, json=admin_payload)

    assert response.status_code == 422


def test_general_user_creation_cannot_create_admin(client, admin_payload):
    response = client.post(
        "/users",
        json={**admin_payload, "role": UserRole.ADMIN.value},
    )

    assert response.status_code in (401, 403)

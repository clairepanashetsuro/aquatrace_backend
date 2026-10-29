from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from core.exceptions import ConflictError

from core.security import hash_password
from database import get_db
from main import app
from models.user import User, UserRole, UserStatus
from services.user_service import UserService

ADMIN_PASSWORD = "AdminTestPass123!"
USER_PASSWORD = "WorkerTestPass123!"
RESET_PASSWORD = "ResetWorkerPass456!"


def create_user(
    db_session,
    email="admin.test@example.com",
    role=UserRole.ADMIN,
    status=UserStatus.ACTIVE,
    password=ADMIN_PASSWORD,
):
    user = User(
        first_name="Test",
        last_name="User",
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=status,
        mfa_enabled=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client, email, password):
    return client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )


def auth_headers(
    client,
    email="admin.test@example.com",
    password=ADMIN_PASSWORD,
):
    response = login(client, email, password)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def user_payload(email="worker.test@example.com"):
    return {
        "first_name": "Test",
        "last_name": "Worker",
        "email": email,
        "password": USER_PASSWORD,
        "role": UserRole.FIELD_OFFICER.value,
    }


def test_login_rejects_unknown_email(client):
    response = login(client, "missing@example.com", USER_PASSWORD)
    assert response.status_code == 401


def test_login_rejects_inactive_account(client, db_session):
    create_user(db_session, status=UserStatus.INACTIVE)
    response = login(client, "admin.test@example.com", ADMIN_PASSWORD)
    assert response.status_code == 401


def test_login_rejects_missing_credentials(client):
    response = client.post("/auth/login", data={})
    assert response.status_code == 422


def test_get_me_returns_authenticated_user(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == "admin.test@example.com"


def test_get_me_rejects_missing_token(client):
    response = client.get("/users/me")
    assert response.status_code == 401


def test_get_me_rejects_invalid_token(client):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_user_can_update_own_profile(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.patch(
        "/users/me",
        headers=headers,
        json={"first_name": "Updated"},
    )

    assert response.status_code == 200
    assert response.json()["first_name"] == "Updated"


def test_user_cannot_set_blank_name(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.patch(
        "/users/me",
        headers=headers,
        json={"first_name": "   "},
    )

    assert response.status_code == 422


def test_user_self_update_rejects_unexpected_fields(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.patch(
        "/users/me",
        headers=headers,
        json={"first_name": "Updated", "role": UserRole.ADMIN.value},
    )

    assert response.status_code == 422
    assert "role" in response.text


def test_admin_can_list_users_with_pagination(client, db_session):
    create_user(db_session)
    create_user(
        db_session,
        email="worker1@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker2@example.com",
        role=UserRole.WATER_QUALITY_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.get("/users?limit=1&offset=0", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 1
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 0


def test_admin_can_filter_users_by_status(client, db_session):
    create_user(db_session)
    create_user(
        db_session,
        email="inactive@example.com",
        role=UserRole.FIELD_OFFICER,
        status=UserStatus.INACTIVE,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.get("/users?status=inactive", headers=headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert all(
        item["status"] == UserStatus.INACTIVE.value for item in response.json()["items"]
    )


def test_list_users_rejects_non_admin(client, db_session):
    create_user(db_session)
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.get("/users", headers=headers)

    assert response.status_code == 403


def test_list_users_rejects_invalid_pagination(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.get("/users?limit=0", headers=headers)

    assert response.status_code == 422


def test_admin_can_create_user(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.post(
        "/users",
        headers=headers,
        json=user_payload(),
    )

    assert response.status_code == 201
    assert response.json()["email"] == "worker.test@example.com"


def test_create_user_rejects_duplicate_email(client, db_session):
    create_user(db_session)
    create_user(
        db_session,
        email="worker.test@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.post(
        "/users",
        headers=headers,
        json=user_payload(),
    )

    assert response.status_code == 409


def test_create_user_rejects_weak_password(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)
    payload = user_payload()
    payload["password"] = "weakpassword123"

    response = client.post(
        "/users",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422


def test_admin_can_get_user_by_id(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.get(
        f"/users/{target.user_id}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == "worker@example.com"


def test_get_user_rejects_unknown_id(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.get(f"/users/{uuid4()}", headers=headers)

    assert response.status_code == 404


def test_get_user_rejects_malformed_id(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.get("/users/not-a-uuid", headers=headers)

    assert response.status_code == 422


def test_admin_can_update_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.patch(
        f"/users/{target.user_id}",
        headers=headers,
        json={"last_name": "Updated"},
    )

    assert response.status_code == 200
    assert response.json()["last_name"] == "Updated"


def test_update_user_rejects_duplicate_email(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="other@example.com",
        role=UserRole.WATER_QUALITY_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.patch(
        f"/users/{target.user_id}",
        headers=headers,
        json={"email": "other@example.com"},
    )

    assert response.status_code == 409


def test_admin_cannot_deactivate_own_account(client, db_session):
    admin = create_user(db_session)
    headers = auth_headers(client)

    response = client.post(
        f"/users/{admin.user_id}/deactivate",
        headers=headers,
    )

    assert response.status_code == 400


def test_last_active_admin_cannot_be_deactivated(db_session):
    admin = create_user(db_session)
    actor = create_user(
        db_session,
        email="field.officer@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )

    with pytest.raises(ConflictError) as exc_info:
        UserService(db_session).deactivate_user(
            admin.user_id,
            actor=actor,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "The last active administrator cannot be deactivated"
    )


def test_admin_can_deactivate_and_reactivate_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    deactivate = client.post(
        f"/users/{target.user_id}/deactivate",
        headers=headers,
    )

    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == UserStatus.INACTIVE.value

    activate = client.post(
        f"/users/{target.user_id}/activate",
        headers=headers,
    )

    assert activate.status_code == 200
    assert activate.json()["status"] == UserStatus.ACTIVE.value


def test_deactivate_unknown_user_returns_404(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.post(
        f"/users/{uuid4()}/deactivate",
        headers=headers,
    )

    assert response.status_code == 404


def test_admin_can_reset_password_and_user_can_log_in(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.post(
        f"/users/{target.user_id}/reset-password",
        headers=headers,
        json={"new_password": RESET_PASSWORD},
    )

    assert response.status_code == 204
    assert (
        login(
            client,
            "worker@example.com",
            RESET_PASSWORD,
        ).status_code
        == 200
    )
    assert (
        login(
            client,
            "worker@example.com",
            USER_PASSWORD,
        ).status_code
        == 401
    )


def test_reset_password_rejects_weak_password(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.post(
        f"/users/{target.user_id}/reset-password",
        headers=headers,
        json={"new_password": "weakpassword123"},
    )

    assert response.status_code == 422


def test_reset_password_rejects_unknown_user(client, db_session):
    create_user(db_session)
    headers = auth_headers(client)

    response = client.post(
        f"/users/{uuid4()}/reset-password",
        headers=headers,
        json={"new_password": RESET_PASSWORD},
    )

    assert response.status_code == 404


def test_database_health_returns_503_when_database_fails(client, db_session):
    previous_override = app.dependency_overrides.get(get_db)

    class BrokenDB:
        def execute(self, statement):
            raise SQLAlchemyError("database unavailable")

    def override_get_db():
        yield BrokenDB()

    app.dependency_overrides[get_db] = override_get_db

    try:
        response = client.get("/health/db")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


def test_non_admin_cannot_create_user(client, db_session):
    create_user(db_session)
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    worker_headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.post(
        "/users",
        headers=worker_headers,
        json=user_payload("new.worker@example.com"),
    )

    assert response.status_code == 403


def test_non_admin_cannot_get_another_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="target@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.get(
        f"/users/{target.user_id}",
        headers=headers,
    )

    assert response.status_code == 403


def test_non_admin_cannot_update_another_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="target@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.patch(
        f"/users/{target.user_id}",
        headers=headers,
        json={"last_name": "Changed"},
    )

    assert response.status_code == 403


def test_non_admin_cannot_deactivate_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="target@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.post(
        f"/users/{target.user_id}/deactivate",
        headers=headers,
    )

    assert response.status_code == 403


def test_non_admin_cannot_activate_user(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="target@example.com",
        role=UserRole.FIELD_OFFICER,
        status=UserStatus.INACTIVE,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.post(
        f"/users/{target.user_id}/activate",
        headers=headers,
    )

    assert response.status_code == 403


def test_non_admin_cannot_reset_user_password(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="target@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(
        client,
        "worker@example.com",
        USER_PASSWORD,
    )

    response = client.post(
        f"/users/{target.user_id}/reset-password",
        headers=headers,
        json={"new_password": RESET_PASSWORD},
    )

    assert response.status_code == 403


def test_admin_can_change_user_role(client, db_session):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.patch(
        f"/users/{target.user_id}",
        headers=headers,
        json={"role": UserRole.WATER_QUALITY_OFFICER.value},
    )

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.WATER_QUALITY_OFFICER.value


def test_create_user_rejects_duplicate_email_with_different_case(
    client,
    db_session,
):
    create_user(db_session)
    create_user(
        db_session,
        email="worker.test@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)
    payload = user_payload("WORKER.TEST@EXAMPLE.COM")

    response = client.post(
        "/users",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 409


def test_update_user_rejects_duplicate_email_with_different_case(
    client,
    db_session,
):
    create_user(db_session)
    target = create_user(
        db_session,
        email="worker@example.com",
        role=UserRole.FIELD_OFFICER,
        password=USER_PASSWORD,
    )
    create_user(
        db_session,
        email="other@example.com",
        role=UserRole.WATER_QUALITY_OFFICER,
        password=USER_PASSWORD,
    )
    headers = auth_headers(client)

    response = client.patch(
        f"/users/{target.user_id}",
        headers=headers,
        json={"email": "OTHER@EXAMPLE.COM"},
    )

    assert response.status_code == 409

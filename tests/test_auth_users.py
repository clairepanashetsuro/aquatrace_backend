from models.user import User, UserRole, UserStatus
from core.security import hash_password


ADMIN_PASSWORD = "AdminTestPass123!"
USER_PASSWORD = "WorkerTestPass123!"


def create_test_admin(db_session):
    admin = User(
        first_name="Test",
        last_name="Administrator",
        email="admin.test@example.com",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        mfa_enabled=False,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def test_admin_can_log_in(client, db_session):
    create_test_admin(db_session)

    response = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": ADMIN_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_login_rejects_incorrect_password(client, db_session):
    create_test_admin(db_session)

    response = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_admin_can_create_user_and_user_can_log_in(client, db_session):
    create_test_admin(db_session)

    admin_login = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": ADMIN_PASSWORD,
        },
    )

    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    create_response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "first_name": "Test",
            "last_name": "Worker",
            "email": "worker.test@example.com",
            "password": USER_PASSWORD,
            "role": UserRole.FIELD_OFFICER.value,
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["email"] == "worker.test@example.com"
    assert create_response.json()["role"] == UserRole.FIELD_OFFICER.value

    user_login = client.post(
        "/auth/login",
        data={
            "username": "worker.test@example.com",
            "password": USER_PASSWORD,
        },
    )

    assert user_login.status_code == 200
    assert user_login.json()["access_token"]


def test_user_creation_requires_admin_authentication(client):
    response = client.post(
        "/users",
        json={
            "first_name": "Test",
            "last_name": "Worker",
            "email": "unauthorized.worker@example.com",
            "password": USER_PASSWORD,
            "role": UserRole.FIELD_OFFICER.value,
        },
    )

    assert response.status_code == 401


def get_admin_access_token(client, db_session):
    create_test_admin(db_session)

    response = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": ADMIN_PASSWORD,
        },
    )

    assert response.status_code == 200
    return response.json()["access_token"]


def test_authenticated_user_can_change_password(client, db_session):
    token = get_admin_access_token(client, db_session)

    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": "UpdatedSecurePass456!",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Password changed successfully"

    old_login = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": ADMIN_PASSWORD,
        },
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        data={
            "username": "admin.test@example.com",
            "password": "UpdatedSecurePass456!",
        },
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


def test_change_password_rejects_incorrect_current_password(client, db_session):
    token = get_admin_access_token(client, db_session)

    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "WrongPassword123!",
            "new_password": "UpdatedSecurePass456!",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is incorrect"


def test_change_password_rejects_weak_new_password(client, db_session):
    token = get_admin_access_token(client, db_session)

    response = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": "password123456",
        },
    )

    assert response.status_code == 422


def test_change_password_requires_authentication(client):
    response = client.post(
        "/auth/change-password",
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": "UpdatedSecurePass456!",
        },
    )

    assert response.status_code == 401

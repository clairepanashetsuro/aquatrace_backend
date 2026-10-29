from cryptography.fernet import Fernet

from core.config import settings
from core.mfa import encrypt_totp_secret, generate_totp_secret, totp_code
from core.security import hash_password
from models.user import User, UserRole, UserStatus


MFA_PASSWORD = "MfaWorkerPass123!"
RECOVERY_CODE = "AB12CD34EF"


def create_mfa_user(db_session, monkeypatch, recovery_codes=None):
    monkeypatch.setattr(
        settings,
        "mfa_encryption_key",
        Fernet.generate_key().decode("utf-8"),
    )

    secret = generate_totp_secret()
    user = User(
        first_name="MFA",
        last_name="Tester",
        email="mfa.tester@example.com",
        password_hash=hash_password(MFA_PASSWORD),
        role=UserRole.FIELD_OFFICER,
        status=UserStatus.ACTIVE,
        mfa_enabled=True,
        totp_secret=encrypt_totp_secret(secret),
        recovery_code_hashes=[hash_password(code) for code in (recovery_codes or [])],
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user, secret


def login_for_mfa(client):
    response = client.post(
        "/auth/login",
        data={
            "username": "mfa.tester@example.com",
            "password": MFA_PASSWORD,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"] is True
    assert data["mfa_token"]
    assert data["access_token"] is None
    assert data["refresh_token"] is None

    return data["mfa_token"]


def test_mfa_login_returns_challenge_without_access_tokens(
    client, db_session, monkeypatch
):
    create_mfa_user(db_session, monkeypatch)

    login_for_mfa(client)


def test_valid_totp_completes_mfa_login(client, db_session, monkeypatch):
    _, secret = create_mfa_user(db_session, monkeypatch)
    challenge = login_for_mfa(client)

    response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": challenge,
            "code": totp_code(secret),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["mfa_required"] is False


def test_invalid_totp_is_rejected(client, db_session, monkeypatch):
    user, secret = create_mfa_user(db_session, monkeypatch)
    challenge = login_for_mfa(client)
    valid_code = totp_code(secret)
    invalid_code = "000000" if valid_code != "000000" else "000001"

    response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": challenge,
            "code": invalid_code,
        },
    )

    assert response.status_code == 401

    db_session.refresh(user)
    assert user.failed_login_attempts == 1
    assert user.mfa_challenge_hash is not None


def test_successful_mfa_challenge_cannot_be_reused(client, db_session, monkeypatch):
    _, secret = create_mfa_user(db_session, monkeypatch)
    challenge = login_for_mfa(client)

    first_response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": challenge,
            "code": totp_code(secret),
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": challenge,
            "code": totp_code(secret),
        },
    )

    assert second_response.status_code == 401


def test_recovery_code_is_consumed_after_use(client, db_session, monkeypatch):
    user, _ = create_mfa_user(
        db_session,
        monkeypatch,
        recovery_codes=[RECOVERY_CODE],
    )

    first_challenge = login_for_mfa(client)

    first_response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": first_challenge,
            "code": RECOVERY_CODE,
        },
    )

    assert first_response.status_code == 200

    db_session.refresh(user)
    assert user.recovery_code_hashes == []

    second_challenge = login_for_mfa(client)

    second_response = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": second_challenge,
            "code": RECOVERY_CODE,
        },
    )

    assert second_response.status_code == 401


def create_unconfigured_user(db_session):
    user = User(
        first_name="MFA",
        last_name="Setup Tester",
        email="mfa.setup@example.com",
        password_hash=hash_password(MFA_PASSWORD),
        role=UserRole.FIELD_OFFICER,
        status=UserStatus.ACTIVE,
        mfa_enabled=False,
        totp_secret=None,
        recovery_code_hashes=[],
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


def test_mfa_setup_returns_secret_uri_and_setup_token(client, db_session, monkeypatch):
    monkeypatch.setattr(
        settings,
        "mfa_encryption_key",
        Fernet.generate_key().decode("utf-8"),
    )
    create_unconfigured_user(db_session)

    login_response = client.post(
        "/auth/login",
        data={
            "username": "mfa.setup@example.com",
            "password": MFA_PASSWORD,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    assert access_token

    response = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["secret"]
    assert data["provisioning_uri"].startswith("otpauth://totp/")
    assert data["setup_token"]


def test_mfa_setup_rejects_invalid_code(client, db_session, monkeypatch):
    monkeypatch.setattr(
        settings,
        "mfa_encryption_key",
        Fernet.generate_key().decode("utf-8"),
    )
    create_unconfigured_user(db_session)

    login_response = client.post(
        "/auth/login",
        data={
            "username": "mfa.setup@example.com",
            "password": MFA_PASSWORD,
        },
    )

    access_token = login_response.json()["access_token"]

    setup_response = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert setup_response.status_code == 200
    setup_token = setup_response.json()["setup_token"]

    valid_code = totp_code(setup_response.json()["secret"])
    invalid_code = "000000" if valid_code != "000000" else "000001"

    response = client.post(
        "/auth/mfa/setup/verify",
        headers={"Authorization": f"Bearer {setup_token}"},
        json={"code": invalid_code},
    )

    assert response.status_code == 400


def test_mfa_setup_enables_mfa_and_returns_recovery_codes(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(
        settings,
        "mfa_encryption_key",
        Fernet.generate_key().decode("utf-8"),
    )
    user = create_unconfigured_user(db_session)

    login_response = client.post(
        "/auth/login",
        data={
            "username": "mfa.setup@example.com",
            "password": MFA_PASSWORD,
        },
    )

    access_token = login_response.json()["access_token"]

    setup_response = client.post(
        "/auth/mfa/setup",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert setup_response.status_code == 200
    setup_data = setup_response.json()

    response = client.post(
        "/auth/mfa/setup/verify",
        headers={"Authorization": f"Bearer {setup_data['setup_token']}"},
        json={"code": totp_code(setup_data["secret"])},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert len(data["recovery_codes"]) == 10
    assert len(set(data["recovery_codes"])) == 10

    db_session.refresh(user)
    assert user.mfa_enabled is True
    assert user.totp_secret is not None
    assert len(user.recovery_code_hashes) == 10


def test_mfa_can_be_disabled_with_password_and_totp(client, db_session, monkeypatch):
    user, secret = create_mfa_user(db_session, monkeypatch)

    login_response = client.post(
        "/auth/login",
        data={
            "username": "mfa.tester@example.com",
            "password": MFA_PASSWORD,
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["access_token"] is None

    challenge = login_for_mfa(client)

    verified_login = client.post(
        "/auth/verify-mfa",
        json={
            "mfa_token": challenge,
            "code": totp_code(secret),
        },
    )

    assert verified_login.status_code == 200
    access_token = verified_login.json()["access_token"]

    response = client.post(
        "/auth/mfa/disable",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "password": MFA_PASSWORD,
            "code": totp_code(secret),
        },
    )

    assert response.status_code == 200

    db_session.refresh(user)
    assert user.mfa_enabled is False
    assert user.totp_secret is None
    assert user.recovery_code_hashes == []
    assert user.mfa_challenge_hash is None
    assert user.mfa_challenge_expires_at is None

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from schemas.auth import LoginResult
from sqlalchemy.orm import Session
from core.exceptions import (
    ConflictError,
    CredentialsError,
    CurrentPasswordError,
    OtpError,
)
from core.mailer import EmailDeliveryError, send_password_reset_otp
from core.mfa import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    provisioning_uri,
    verify_totp,
)
from core.security import (
    MFA_CHALLENGE_MINUTES,
    InvalidTokenError,
    create_access_token,
    create_mfa_challenge_token,
    create_mfa_setup_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from models.user import User, UserStatus
from repositories.user_repository import UserRepository


logger = logging.getLogger(__name__)

AUTH_ERROR = "Invalid email or password"
RESET_CODE_ERROR = "Invalid or expired password reset code"
REFRESH_TOKEN_ERROR = "Invalid or expired refresh token"

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15
PASSWORD_RESET_OTP_MINUTES = 10
MAX_PASSWORD_RESET_ATTEMPTS = 5


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def hmac_compare_digest(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def authenticate_user(
    email: str,
    password: str,
    db: Session,
    ip_address: str | None = None,
) -> User:
    repository = UserRepository(db)
    normalized_email = email.strip().lower()
    user = repository.get_by_email(normalized_email)
    now = datetime.now(timezone.utc)

    if user is not None and user.locked_until is not None:
        locked_until = _utc_datetime(user.locked_until)

        if locked_until > now:
            repository.commit()
            raise CredentialsError(detail=AUTH_ERROR)

        user.locked_until = None
        user.failed_login_attempts = 0

    valid_password = (
        user is not None
        and bool(user.password_hash)
        and verify_password(password, user.password_hash)
    )
    valid_account = user is not None and user.status == UserStatus.ACTIVE

    if not valid_password or not valid_account:
        if user is not None and valid_account:
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)

        repository.commit()
        raise CredentialsError(detail=AUTH_ERROR)

    user.failed_login_attempts = 0
    user.locked_until = None
    repository.flush()

    return user


def request_password_reset(email: str, db: Session) -> None:
    repository = UserRepository(db)
    normalized_email = email.strip().lower()
    user = repository.get_by_email(normalized_email)

    if user is None or user.status != UserStatus.ACTIVE or not user.password_hash:
        return

    otp = f"{secrets.randbelow(1_000_000):06d}"

    user.otp_hash = hash_password(otp)
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=PASSWORD_RESET_OTP_MINUTES
    )
    user.otp_attempts = 0

    repository.commit()

    try:
        send_password_reset_otp(str(user.email), otp)
    except EmailDeliveryError:
        logger.exception("Password reset email delivery failed")
        user.otp_hash = None
        user.otp_expires_at = None
        user.otp_attempts = 0
        repository.commit()


def reset_password(
    email: str,
    otp_code: str,
    new_password: str,
    db: Session,
) -> None:
    repository = UserRepository(db)
    user = repository.get_by_email(email.strip().lower())

    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or not user.password_hash
        or not user.otp_hash
        or not user.otp_expires_at
    ):
        raise OtpError(detail=RESET_CODE_ERROR)

    now = datetime.now(timezone.utc)
    expires_at = _utc_datetime(user.otp_expires_at)

    if expires_at <= now:
        _clear_password_reset_otp(user)
        repository.commit()
        raise OtpError(detail=RESET_CODE_ERROR)

    if user.otp_attempts >= MAX_PASSWORD_RESET_ATTEMPTS:
        _clear_password_reset_otp(user)
        repository.commit()
        raise OtpError(detail=RESET_CODE_ERROR)

    if not verify_password(otp_code, user.otp_hash):
        user.otp_attempts += 1

        if user.otp_attempts >= MAX_PASSWORD_RESET_ATTEMPTS:
            _clear_password_reset_otp(user)

        repository.commit()
        raise OtpError(detail=RESET_CODE_ERROR)

    user.password_hash = hash_password(new_password)
    _clear_password_reset_otp(user)
    repository.commit()


def _clear_password_reset_otp(user: User) -> None:
    user.otp_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0


def refresh_tokens(refresh_token: str, db: Session) -> tuple[str, str]:
    repository = UserRepository(db)
    try:
        token_payload = decode_refresh_token(refresh_token)
        user_id = UUID(token_payload["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise CredentialsError(detail=REFRESH_TOKEN_ERROR) from None

    user = repository.get_by_id(user_id)

    if user is None or user.status != UserStatus.ACTIVE:
        raise CredentialsError(detail=REFRESH_TOKEN_ERROR)

    return (
        create_access_token(str(user.user_id)),
        create_refresh_token(str(user.user_id)),
    )


def change_password(
    current_user: User,
    current_password: str,
    new_password: str,
    db: Session,
) -> None:
    repository = UserRepository(db)
    if not current_user.password_hash or not verify_password(
        current_password,
        current_user.password_hash,
    ):
        raise CurrentPasswordError()

    current_user.password_hash = hash_password(new_password)
    repository.commit()


def verify_mfa_challenge(
    token: str,
    code: str,
    db: Session,
    ip_address: str | None = None,
) -> User:
    repository = UserRepository(db)

    def invalid_challenge() -> CredentialsError:
        return CredentialsError(detail="Invalid or expired MFA challenge")

    try:
        payload = decode_token(
            token,
            required_claims=["sub", "iat", "exp", "iss", "token_use"],
        )

        if payload.get("token_use") != "mfa_challenge":
            raise invalid_challenge()

        user_id = UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise invalid_challenge() from None

    user = repository.get_by_id(user_id)

    if (
        user is None
        or user.status != UserStatus.ACTIVE
        or not user.mfa_enabled
        or not user.totp_secret
        or not user.mfa_challenge_hash
        or not user.mfa_challenge_expires_at
        or not hmac_compare_digest(
            user.mfa_challenge_hash,
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
        )
    ):
        raise invalid_challenge()

    now = datetime.now(timezone.utc)
    challenge_expires_at = _utc_datetime(user.mfa_challenge_expires_at)

    if challenge_expires_at <= now:
        user.mfa_challenge_hash = None
        user.mfa_challenge_expires_at = None
        repository.commit()
        raise invalid_challenge()

    if user.locked_until is not None:
        locked_until = _utc_datetime(user.locked_until)

        if locked_until > now:
            raise invalid_challenge()

    secret = decrypt_totp_secret(user.totp_secret)

    if verify_totp(secret, code):
        user.mfa_challenge_hash = None
        user.mfa_challenge_expires_at = None
        user.failed_login_attempts = 0
        user.locked_until = None
        repository.commit()
        return user

    recovery_code = code.strip().upper()
    hashes = list(user.recovery_code_hashes or [])

    if len(recovery_code) == 10:
        for index, stored_hash in enumerate(hashes):
            if verify_password(recovery_code, stored_hash):
                hashes.pop(index)
                user.recovery_code_hashes = hashes
                user.mfa_challenge_hash = None
                user.mfa_challenge_expires_at = None
                user.failed_login_attempts = 0
                user.locked_until = None
                repository.commit()
                return user

    user.failed_login_attempts += 1

    if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)

    repository.commit()
    raise CredentialsError(detail="Invalid MFA code")


def login_user(
    email: str,
    password: str,
    db: Session,
    ip_address: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    repository = UserRepository(db)
    user = authenticate_user(
        email=email,
        password=password,
        db=db,
        ip_address=ip_address,
    )

    if user.mfa_enabled:
        if not user.totp_secret:
            raise CredentialsError(detail=AUTH_ERROR)

        challenge_token = create_mfa_challenge_token(str(user.user_id))
        user.mfa_challenge_hash = hashlib.sha256(
            challenge_token.encode("utf-8")
        ).hexdigest()
        user.mfa_challenge_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=MFA_CHALLENGE_MINUTES
        )
        repository.commit()

        return None, None, challenge_token

    return (
        create_access_token(str(user.user_id)),
        create_refresh_token(str(user.user_id)),
        None,
    )


def authenticate_and_create_login_result(
    email: str,
    password: str,
    db: Session,
    ip_address: str | None = None,
) -> LoginResult:
    access_token, refresh_token, mfa_token = login_user(
        email=email,
        password=password,
        db=db,
        ip_address=ip_address,
    )

    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
        mfa_required=mfa_token is not None,
        mfa_token=mfa_token,
    )


def complete_mfa_login(
    token: str,
    code: str,
    db: Session,
    ip_address: str | None = None,
) -> tuple[str, str]:
    user = verify_mfa_challenge(
        token=token,
        code=code,
        db=db,
        ip_address=ip_address,
    )

    return (
        create_access_token(str(user.user_id)),
        create_refresh_token(str(user.user_id)),
    )


def start_mfa_setup(current_user: User, db: Session) -> tuple[str, str, str]:
    repository = UserRepository(db)
    user = repository.get_by_id(current_user.user_id)

    if user is None or user.status != UserStatus.ACTIVE:
        raise CredentialsError(detail="Invalid or inactive account")

    if user.mfa_enabled:
        raise ConflictError(detail="MFA is already enabled")

    secret = generate_totp_secret()
    user.totp_secret = encrypt_totp_secret(secret)
    user.recovery_code_hashes = []
    repository.commit()

    setup_token = create_mfa_setup_token(str(user.user_id))
    return secret, provisioning_uri(secret, user.email), setup_token


def verify_mfa_setup(
    current_user: User,
    code: str,
    db: Session,
) -> list[str]:
    repository = UserRepository(db)
    user = repository.get_by_id(current_user.user_id)

    if user is None or user.status != UserStatus.ACTIVE:
        raise CredentialsError(detail="Invalid or inactive account")

    if user.mfa_enabled:
        raise ConflictError(detail="MFA is already enabled")

    if not user.totp_secret:
        raise OtpError(detail="Start MFA setup before verifying a code")

    secret = decrypt_totp_secret(user.totp_secret)

    if not verify_totp(secret, code):
        raise OtpError(detail="Invalid authenticator code")

    recovery_codes = [secrets.token_hex(5).upper() for _ in range(10)]
    user.recovery_code_hashes = [
        hash_password(recovery_code) for recovery_code in recovery_codes
    ]
    user.mfa_enabled = True
    user.mfa_challenge_hash = None
    user.mfa_challenge_expires_at = None
    repository.commit()

    return recovery_codes


def disable_mfa(
    current_user: User,
    password: str,
    code: str,
    db: Session,
) -> None:
    repository = UserRepository(db)
    user = repository.get_by_id(current_user.user_id)

    if user is None or user.status != UserStatus.ACTIVE:
        raise CredentialsError(detail="Invalid or inactive account")

    if not user.password_hash or not verify_password(password, user.password_hash):
        raise CurrentPasswordError()

    if not user.mfa_enabled or not user.totp_secret:
        raise ConflictError(detail="MFA is not enabled")

    secret = decrypt_totp_secret(user.totp_secret)

    if not verify_totp(secret, code):
        recovery_code = code.strip().upper()
        hashes = list(user.recovery_code_hashes or [])
        matched_index = next(
            (
                index
                for index, stored_hash in enumerate(hashes)
                if len(recovery_code) == 10
                and verify_password(recovery_code, stored_hash)
            ),
            None,
        )

        if matched_index is None:
            raise OtpError(detail="Invalid authenticator or recovery code")

    user.mfa_enabled = False
    user.totp_secret = None
    user.recovery_code_hashes = []
    user.mfa_challenge_hash = None
    user.mfa_challenge_expires_at = None
    repository.commit()

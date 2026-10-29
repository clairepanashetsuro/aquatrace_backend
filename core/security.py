from datetime import datetime, timedelta, timezone
from typing import Any
from functools import lru_cache
import secrets
import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pathlib import Path

from core.config import settings


password_hash = PasswordHash.recommended()

MFA_CHALLENGE_MINUTES = 5
MFA_SETUP_MINUTES = 10


@lru_cache(maxsize=1)
def _read_private_key() -> str:
    key = settings.jwt_private_key

    if key:
        return key.replace("\\n", "\n").strip()

    path = settings.jwt_private_key_path

    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()

    raise ValueError("JWT private key is not configured through a value or file path")


@lru_cache(maxsize=1)
def _read_public_key() -> str:
    key = settings.jwt_public_key

    if key:
        return key.replace("\\n", "\n").strip()

    path = settings.jwt_public_key_path

    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()

    raise ValueError("JWT public key is not configured through a value or file path")


def hash_password(plain_password: str) -> str:
    return password_hash.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False

    try:
        return password_hash.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_token(
    subject: str,
    token_use: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.jwt_issuer,
        "token_use": token_use,
    }

    if extra_claims:
        protected_claims = {"sub", "iat", "exp", "iss", "token_use"}
        if protected_claims.intersection(extra_claims):
            raise ValueError("Extra claims cannot override standard JWT claims")
        payload.update(extra_claims)

    return jwt.encode(payload, _read_private_key(), algorithm="RS256")


def create_access_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_use="access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_use="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_days),
        extra_claims={"jti": secrets.token_urlsafe(32)},
    )


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = decode_token(
        token,
        required_claims=["sub", "iat", "exp", "iss", "token_use", "jti"],
    )

    if payload.get("token_use") != "refresh":
        raise InvalidTokenError("Invalid refresh token")

    return payload


def create_mfa_challenge_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_use="mfa_challenge",
        expires_delta=timedelta(minutes=MFA_CHALLENGE_MINUTES),
    )


def create_mfa_setup_token(subject: str) -> str:
    return create_token(
        subject=subject,
        token_use="mfa_setup",
        expires_delta=timedelta(minutes=MFA_SETUP_MINUTES),
    )


def decode_token(
    token: str,
    required_claims: list[str] | None = None,
) -> dict[str, Any]:
    options = {}

    if required_claims:
        options["require"] = required_claims

    return jwt.decode(
        token,
        _read_public_key(),
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
        options=options,
    )


__all__ = [
    "InvalidTokenError",
    "create_access_token",
    "create_mfa_challenge_token",
    "create_mfa_setup_token",
    "create_refresh_token",
    "create_token",
    "decode_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]

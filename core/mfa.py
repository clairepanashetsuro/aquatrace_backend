import base64
import hashlib
import hmac
import struct
import time
import secrets
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from core.exceptions import ApplicationError, ServiceUnavailableError

from core.config import settings


def _fernet() -> Fernet:
    key = settings.mfa_encryption_key
    if not key:
        raise ServiceUnavailableError(detail="MFA is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError):
        raise ServiceUnavailableError(detail="MFA is not configured") from None


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_totp_secret(encrypted_secret: str) -> str:
    try:
        return _fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        raise ApplicationError(
            detail="MFA configuration could not be read",
            status_code=500,
        ) from None


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def verify_totp(secret: str, code: str, now: int | None = None) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    current = int(time.time()) if now is None else now
    return any(
        hmac.compare_digest(totp_code(secret, current + offset * 30), code)
        for offset in (-1, 0, 1)
    )


def provisioning_uri(secret: str, email: str) -> str:
    issuer = "AquaTrace"
    label = quote(f"{issuer}:{email}", safe="")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
        }
    )
    return f"otpauth://totp/{label}?{query}"

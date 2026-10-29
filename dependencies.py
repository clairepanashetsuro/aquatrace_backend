from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.security import InvalidTokenError, decode_token
from database import get_db
from models.user import User, UserRole, UserStatus
from repositories.user_repository import UserRepository


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(
            credentials.credentials,
            required_claims=["sub", "iat", "exp", "iss"],
        )

        if payload.get("token_use", "access") != "access":
            raise unauthorized

        user_id = UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise unauthorized from None

    user = UserRepository(db).get_by_id(user_id)

    if user is None or user.status != UserStatus.ACTIVE:
        raise unauthorized

    return user


def get_current_user_for_mfa_setup(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired MFA setup token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = decode_token(
            credentials.credentials,
            required_claims=["sub", "iat", "exp", "iss", "token_use"],
        )

        if payload.get("token_use") != "mfa_setup":
            raise unauthorized

        user_id = UUID(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError):
        raise unauthorized from None

    user = UserRepository(db).get_by_id(user_id)

    if user is None or user.status != UserStatus.ACTIVE or user.mfa_enabled:
        raise unauthorized

    return user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )

    return current_user


def require_water_quality_officer(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.WATER_QUALITY_OFFICER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Water Quality Officer privileges required",
        )

    return current_user

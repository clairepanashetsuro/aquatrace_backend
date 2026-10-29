import secrets

from fastapi import Header, HTTPException, status

from core.config import settings


def require_gps_integration(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected_key = settings.gps_integration_api_key

    if (
        not expected_key
        or not x_api_key
        or not secrets.compare_digest(x_api_key, expected_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GPS integration credentials",
            headers={"WWW-Authenticate": "ApiKey"},
        )

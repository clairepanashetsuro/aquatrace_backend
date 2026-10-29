from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value):
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        return value

    frontend_origin: str | None = None

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            return [
                origin.strip().rstrip("/")
                for origin in value.split(",")
                if origin.strip()
            ]
        return value

    jwt_private_key: str | None = None
    jwt_public_key: str | None = None

    jwt_private_key_path: Path | None = Field(
        default=PROJECT_ROOT / "secrets" / "jwt-private.pem"
    )
    jwt_public_key_path: Path | None = Field(
        default=PROJECT_ROOT / "secrets" / "jwt-public.pem"
    )

    jwt_access_token_minutes: int = Field(default=30, ge=1, le=1440)
    jwt_refresh_token_days: int = Field(default=1, ge=1, le=90)

    jwt_issuer: str = "aquatrace-api"
    jwt_audience: str = "aquatrace-api"

    oauth_client_id: str = "aquatrace-pwa"
    oauth_redirect_uri: str | None = None
    oauth_frontend_origin: str | None = None
    oauth_authorization_code_minutes: int = Field(default=5, ge=1, le=10)

    mfa_encryption_key: str | None = None
    locationiq_api_key: str | None = None
    gps_integration_api_key: str | None = None

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_file_search_store_name: str | None = None


settings = Settings()

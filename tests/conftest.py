import os
import uuid
from typing import Generator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from core.config import settings
from core.rate_limiter import limiter
from core.security import _read_private_key, _read_public_key
from database import Base, get_db
from main import app
from models.alert import Alert
from models.audit_log import AuditLog
from models.device import Device
from models.sensor_reading import SensorReading
from models.user import User, UserRole


@compiles(ARRAY, "sqlite")
def compile_array_for_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def compile_inet_for_sqlite(element, compiler, **kw):
    return "VARCHAR(45)"


@pytest.fixture(scope="session", autouse=True)
def temporary_jwt_keys(tmp_path_factory):
    key_directory = tmp_path_factory.mktemp("jwt-keys")
    private_key_path = key_directory / "jwt-private.pem"
    public_key_path = key_directory / "jwt-public.pem"

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    original_private_path = settings.jwt_private_key_path
    original_public_path = settings.jwt_public_key_path

    settings.jwt_private_key_path = private_key_path
    settings.jwt_public_key_path = public_key_path

    _read_private_key.cache_clear()
    _read_public_key.cache_clear()

    yield

    _read_private_key.cache_clear()
    _read_public_key.cache_clear()

    settings.jwt_private_key_path = original_private_path
    settings.jwt_public_key_path = original_public_path


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="session", autouse=True)
def force_testing_environment():
    os.environ["TESTING"] = "true"
    yield


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    recovery_code_column = User.__table__.c.recovery_code_hashes
    original_type = recovery_code_column.type
    recovery_code_column.type = JSON()

    tables = [
        User.__table__,
        Device.__table__,
        SensorReading.__table__,
        Alert.__table__,
        AuditLog.__table__,
    ]

    try:
        Base.metadata.create_all(
            bind=engine,
            tables=tables,
        )
        yield engine
    finally:
        try:
            Base.metadata.drop_all(
                bind=engine,
                tables=list(reversed(tables)),
            )
        finally:
            recovery_code_column.type = original_type
            engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    session = testing_session_local()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session, test_engine, monkeypatch):
    from core import http_audit_middleware

    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )

    monkeypatch.setattr(
        http_audit_middleware,
        "SessionLocal",
        testing_session_local,
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session: Session) -> User:
    user = User(
        user_id=uuid.uuid4(),
        first_name="Admin",
        last_name="User",
        email=f"{uuid.uuid4()}@example.com",
        role=UserRole.ADMIN,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def water_quality_officer_user(db_session: Session) -> User:
    user = User(
        user_id=uuid.uuid4(),
        first_name="WQO",
        last_name="User",
        email=f"{uuid.uuid4()}@example.com",
        role=UserRole.WATER_QUALITY_OFFICER,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def field_officer_user(db_session: Session) -> User:
    user = User(
        user_id=uuid.uuid4(),
        first_name="FO",
        last_name="User",
        email=f"{uuid.uuid4()}@example.com",
        role=UserRole.FIELD_OFFICER,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user

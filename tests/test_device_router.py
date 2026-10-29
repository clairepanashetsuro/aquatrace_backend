from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from database import Base, get_db
from dependencies import get_current_user
from models.device import Device, DeviceStatus
from models.user import User, UserRole


@compiles(ARRAY, "sqlite")
def compile_array_for_sqlite(element, compiler, **kw):
    return "TEXT"


@compiles(INET, "sqlite")
def compile_inet_for_sqlite(element, compiler, **kw):
    return "VARCHAR(45)"


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        bind=engine,
        tables=[User.__table__, Device.__table__],
    )

    yield engine

    Base.metadata.drop_all(
        bind=engine,
        tables=[Device.__table__, User.__table__],
    )
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    testing_session_local = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    session = testing_session_local()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app = FastAPI()

    from routers.device import router as device_router

    app.include_router(device_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def gps_headers(monkeypatch):
    test_api_key = "test-gps-integration-key"

    monkeypatch.setattr(
        settings,
        "gps_integration_api_key",
        test_api_key,
    )

    return {"X-API-Key": test_api_key}


def _make_user(
    db_session: Session,
    **kwargs,
) -> User:
    user = User(
        user_id=uuid4(),
        first_name="Test",
        last_name="User",
        email=f"{uuid4()}@example.com",
        role=kwargs.pop("role", UserRole.ADMIN),
        status=kwargs.pop("status", "active"),
        **kwargs,
    )
    db_session.add(user)
    db_session.commit()
    return user


def authenticate_as(client: TestClient, user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: user


def _make_device(
    db_session: Session,
    user: User | None = None,
    serial_number: str = "SER-ROUTER",
    **kwargs,
) -> Device:
    owner = user or _make_user(db_session)

    defaults = {
        "latitude": 1.0,
        "longitude": 2.0,
        "address": "Test address",
        "description": None,
        "status": DeviceStatus.ACTIVE,
    }
    defaults.update(kwargs)

    device = Device(
        user_id=owner.user_id,
        serial_number=serial_number,
        **defaults,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


class TestDeviceRouter:
    def test_create_device_endpoint(self, db_session, client):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-API-001",
                "latitude": -1.9441,
                "longitude": 30.0619,
                "address": "Kigali, Rwanda",
                "description": "Test device",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["serial_number"] == "SER-API-001"
        assert data["status"] == "active"
        assert data["description"] == "Test device"
        assert data["latitude"] == pytest.approx(-1.9441)
        assert data["longitude"] == pytest.approx(30.0619)
        assert data["address"] == "Kigali, Rwanda"
        assert data["user_id"] == str(user.user_id)
        assert "location_id" not in data

    def test_create_device_without_coordinates(self, db_session, client):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={"serial_number": "SER-NO-GPS"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["serial_number"] == "SER-NO-GPS"
        assert data["latitude"] is None
        assert data["longitude"] is None
        assert data["address"] is None

    def test_create_device_rejects_latitude_without_longitude(
        self,
        db_session,
        client,
    ):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-PARTIAL-GPS",
                "latitude": -1.9441,
            },
        )

        assert response.status_code == 422

    def test_create_device_invalid_latitude(self, db_session, client):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-BAD-LAT",
                "latitude": 91,
                "longitude": 30,
            },
        )

        assert response.status_code == 422

    def test_create_device_invalid_longitude(self, db_session, client):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-BAD-LON",
                "latitude": -1,
                "longitude": 181,
            },
        )

        assert response.status_code == 422

    def test_create_device_requires_authentication(self, client):
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-NO-AUTH",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role",
        [UserRole.ADMIN, UserRole.FIELD_OFFICER],
    )
    def test_create_device_rejects_unauthorized_roles(
        self,
        db_session,
        client,
        role,
    ):
        user = _make_user(db_session, role=role)
        authenticate_as(client, user)

        response = client.post(
            "/api/v1/devices",
            json={"serial_number": f"SER-FORBIDDEN-{role.name}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Water Quality Officer privileges required"

    def test_list_devices_endpoint(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)
        _make_device(db_session, user=user)

        response = client.get("/api/v1/devices")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "SER-ROUTER"
        assert data[0]["latitude"] == pytest.approx(1.0)
        assert data[0]["longitude"] == pytest.approx(2.0)

    def test_list_devices_requires_authentication(self, client):
        response = client.get("/api/v1/devices")
        assert response.status_code == 401

    def test_list_devices_filter_by_status(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)

        _make_device(
            db_session,
            user=user,
            serial_number="SER-ACTIVE",
        )
        _make_device(
            db_session,
            user=user,
            serial_number="SER-INACTIVE",
            status=DeviceStatus.INACTIVE,
        )

        response = client.get("/api/v1/devices?status=inactive")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["serial_number"] == "SER-INACTIVE"
        assert data[0]["status"] == "inactive"

    def test_get_device_endpoint(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)
        device = _make_device(db_session, user=user)

        response = client.get(f"/api/v1/devices/{device.device_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == str(device.device_id)
        assert data["address"] == "Test address"

    def test_get_device_requires_authentication(
        self,
        db_session,
        client,
    ):
        user = _make_user(db_session)
        device = _make_device(db_session, user=user)

        response = client.get(f"/api/v1/devices/{device.device_id}")
        assert response.status_code == 401

    def test_get_device_not_found(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)

        response = client.get("/api/v1/devices/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_update_device_endpoint(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)
        device = _make_device(db_session, user=user)

        response = client.patch(
            f"/api/v1/devices/{device.device_id}",
            json={
                "status": "inactive",
                "description": "Updated device",
                "latitude": -2.0,
                "longitude": 29.5,
                "address": "Updated address",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"
        assert data["description"] == "Updated device"
        assert data["latitude"] == pytest.approx(-2.0)
        assert data["longitude"] == pytest.approx(29.5)
        assert data["address"] == "Updated address"

    def test_update_device_rejects_partial_coordinates(
        self,
        db_session,
        client,
    ):
        user = _make_user(db_session)
        authenticate_as(client, user)
        device = _make_device(db_session, user=user)

        response = client.patch(
            f"/api/v1/devices/{device.device_id}",
            json={"latitude": -2.0},
        )

        assert response.status_code == 422

    def test_update_device_rejects_mismatched_null_coordinates(
        self,
        db_session,
        client,
    ):
        user = _make_user(db_session)
        authenticate_as(client, user)
        device = _make_device(db_session, user=user)

        response = client.patch(
            f"/api/v1/devices/{device.device_id}",
            json={
                "latitude": None,
                "longitude": 29.5,
            },
        )

        assert response.status_code == 422

    def test_duplicate_serial_rejected(self, db_session, client):
        user = _make_user(
            db_session,
            role=UserRole.WATER_QUALITY_OFFICER,
        )
        authenticate_as(client, user)
        _make_device(
            db_session,
            user=user,
            serial_number="SER-DUP",
        )

        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "SER-DUP",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 409
        assert "Serial number already registered" in response.json()["detail"]

    def test_update_duplicate_serial_rejected(
        self,
        db_session,
        client,
    ):
        user = _make_user(db_session)
        authenticate_as(client, user)

        _make_device(
            db_session,
            user=user,
            serial_number="SER-ONE",
        )
        second = _make_device(
            db_session,
            user=user,
            serial_number="SER-TWO",
        )

        response = client.patch(
            f"/api/v1/devices/{second.device_id}",
            json={"serial_number": "SER-ONE"},
        )

        assert response.status_code == 409

    def test_delete_device_endpoint(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)
        device = _make_device(db_session, user=user)

        response = client.delete(f"/api/v1/devices/{device.device_id}")
        assert response.status_code == 204

        response = client.get(f"/api/v1/devices/{device.device_id}")
        assert response.status_code == 404

    def test_delete_device_not_found(self, db_session, client):
        user = _make_user(db_session)
        authenticate_as(client, user)

        response = client.delete("/api/v1/devices/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 404

    def test_gps_endpoint_requires_api_key(self, client):
        response = client.patch(
            "/api/v1/devices/gps",
            json={
                "serial_number": "AQUA-GPS-001",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 401

    def test_gps_endpoint_rejects_invalid_api_key(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setattr(
            settings,
            "gps_integration_api_key",
            "expected-test-key",
        )

        response = client.patch(
            "/api/v1/devices/gps",
            headers={"X-API-Key": "wrong-test-key"},
            json={
                "serial_number": "AQUA-GPS-001",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 401

    def test_gps_endpoint_updates_device(
        self,
        db_session,
        client,
        monkeypatch,
        gps_headers,
    ):
        user = _make_user(db_session)
        device = _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-001",
            address="Old address",
        )

        from services.device import DeviceService

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: "Kigali, Rwanda"),
        )

        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": "AQUA-GPS-001",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == str(device.device_id)
        assert data["latitude"] == pytest.approx(-1.9441)
        assert data["longitude"] == pytest.approx(30.0619)
        assert data["address"] == "Kigali, Rwanda"
        assert data["last_seen_at"] is not None

    def test_gps_endpoint_updates_device_without_previous_coordinates(
        self,
        db_session,
        client,
        monkeypatch,
        gps_headers,
    ):
        user = _make_user(db_session)
        device = _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-FIRST",
            latitude=None,
            longitude=None,
            address=None,
        )

        from services.device import DeviceService

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: "Kigali, Rwanda"),
        )

        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": "AQUA-GPS-FIRST",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["device_id"] == str(device.device_id)
        assert data["latitude"] == pytest.approx(-1.9441)
        assert data["longitude"] == pytest.approx(30.0619)
        assert data["address"] == "Kigali, Rwanda"
        assert data["last_seen_at"] is not None

    def test_gps_endpoint_preserves_address_if_geocoding_fails(
        self,
        db_session,
        client,
        monkeypatch,
        gps_headers,
    ):
        user = _make_user(db_session)
        _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-NO-GEOCODE",
            address="Previous address",
        )

        from services.device import DeviceService

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: None),
        )

        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": "AQUA-GPS-NO-GEOCODE",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["address"] == "Previous address"
        assert data["latitude"] == pytest.approx(-1.9441)
        assert data["longitude"] == pytest.approx(30.0619)

    def test_gps_endpoint_returns_404_for_unknown_serial(
        self,
        client,
        gps_headers,
    ):
        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": "UNKNOWN-DEVICE",
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Device not found"

    def test_gps_endpoint_rejects_invalid_coordinates(
        self,
        client,
        gps_headers,
    ):
        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": "AQUA-GPS-BAD",
                "latitude": 95,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "device_status",
        [DeviceStatus.INACTIVE, DeviceStatus.REVOKED],
    )
    def test_gps_endpoint_rejects_non_active_device(
        self,
        db_session,
        client,
        device_status,
        gps_headers,
    ):
        user = _make_user(db_session)
        serial_number = f"AQUA-GPS-{device_status.value.upper()}"

        _make_device(
            db_session,
            user=user,
            serial_number=serial_number,
            status=device_status,
            revoked_at=(
                datetime.now(timezone.utc)
                if device_status == DeviceStatus.REVOKED
                else None
            ),
        )

        response = client.patch(
            "/api/v1/devices/gps",
            headers=gps_headers,
            json={
                "serial_number": serial_number,
                "latitude": -1.9441,
                "longitude": 30.0619,
            },
        )

        assert response.status_code == 409

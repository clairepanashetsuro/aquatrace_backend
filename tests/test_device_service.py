from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.device import Device, DeviceStatus
from models.user import User, UserRole
from schemas.device import DeviceCreate, DeviceGPSUpdate, DeviceUpdate
from services.device import DeviceService


def _make_user(db_session: Session, email: str | None = None) -> User:
    user = User(
        user_id=uuid4(),
        first_name="Test",
        last_name="User",
        email=email or f"{uuid4()}@example.com",
        role=UserRole.ADMIN,
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_device(
    db_session: Session,
    user: User | None = None,
    **kwargs,
) -> Device:
    owner = user or _make_user(db_session)

    defaults = {
        "user_id": owner.user_id,
        "serial_number": f"SER-{uuid4().hex[:12]}",
        "latitude": 1.0,
        "longitude": 2.0,
        "address": "Test address",
        "description": None,
        "status": DeviceStatus.ACTIVE,
    }
    defaults.update(kwargs)

    device = Device(**defaults)
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


class TestCreateDevice:
    def test_create_device(self, db_session: Session):
        user = _make_user(db_session, "device-create@example.com")

        data = DeviceCreate(
            serial_number="SER-SVC-CREATE",
            latitude=1.0,
            longitude=2.0,
            address="Test address",
            description="Test device",
        )

        device = DeviceService(db_session).create_device(
            data,
            current_user=user,
        )

        assert device.user_id == user.user_id
        assert device.serial_number == "SER-SVC-CREATE"
        assert device.status == DeviceStatus.ACTIVE
        assert device.latitude == pytest.approx(1.0)
        assert device.longitude == pytest.approx(2.0)
        assert device.address == "Test address"
        assert device.description == "Test device"

    def test_create_device_without_coordinates(self, db_session: Session):
        user = _make_user(db_session, "device-no-gps@example.com")

        device = DeviceService(db_session).create_device(
            DeviceCreate(serial_number="SER-SVC-NO-GPS"),
            current_user=user,
        )

        assert device.latitude is None
        assert device.longitude is None
        assert device.address is None

    def test_create_device_rejects_duplicate_serial(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session, "device-dup@example.com")
        service = DeviceService(db_session)

        data = DeviceCreate(
            serial_number="SER-SVC-DUP",
            latitude=1.0,
            longitude=2.0,
        )

        service.create_device(data, current_user=user)

        with pytest.raises(HTTPException) as exc:
            service.create_device(data, current_user=user)

        assert exc.value.status_code == 409
        assert exc.value.detail == "Serial number already registered"

    def test_create_device_rejects_inactive_user(
        self,
        db_session: Session,
    ):
        user = _make_user(
            db_session,
            "device-inactive-user@example.com",
        )
        user.status = "inactive"
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).create_device(
                DeviceCreate(
                    serial_number="SER-INACTIVE-USER",
                    latitude=1.0,
                    longitude=2.0,
                ),
                current_user=user,
            )

        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication required"


class TestUpdateDevice:
    def test_update_device_returns_404_when_missing(
        self,
        db_session: Session,
    ):
        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).update_device(
                uuid4(),
                DeviceUpdate(status="inactive"),
            )

        assert exc.value.status_code == 404
        assert exc.value.detail == "Device not found"

    def test_update_device_status_revoked_sets_revoked_at(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session, "device-status-rev@example.com")
        device = _make_device(db_session, user=user)

        updated = DeviceService(db_session).update_device(
            device.device_id,
            DeviceUpdate(status="revoked"),
        )

        assert updated.status == DeviceStatus.REVOKED
        assert updated.revoked_at is not None

    def test_update_device_status_active_clears_revoked_at(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session, "device-status-active@example.com")
        device = _make_device(db_session, user=user)

        device.status = DeviceStatus.REVOKED
        device.revoked_at = datetime.now(timezone.utc)
        db_session.commit()

        updated = DeviceService(db_session).update_device(
            device.device_id,
            DeviceUpdate(status="active"),
        )

        assert updated.status == DeviceStatus.ACTIVE
        assert updated.revoked_at is None

    def test_update_device_description(self, db_session: Session):
        user = _make_user(db_session, "device-description@example.com")
        device = _make_device(db_session, user=user)

        updated = DeviceService(db_session).update_device(
            device.device_id,
            DeviceUpdate(description="new description"),
        )

        assert updated.description == "new description"

    def test_update_device_location_fields(self, db_session: Session):
        user = _make_user(
            db_session,
            "device-update-location@example.com",
        )
        device = _make_device(db_session, user=user)

        updated = DeviceService(db_session).update_device(
            device.device_id,
            DeviceUpdate(
                latitude=-2.0,
                longitude=29.5,
                address="Updated address",
            ),
        )

        assert updated.latitude == pytest.approx(-2.0)
        assert updated.longitude == pytest.approx(29.5)
        assert updated.address == "Updated address"

    def test_update_device_rejects_duplicate_serial(
        self,
        db_session: Session,
    ):
        user = _make_user(
            db_session,
            "device-update-duplicate@example.com",
        )
        _make_device(
            db_session,
            user=user,
            serial_number="SER-EXISTING",
        )
        second = _make_device(
            db_session,
            user=user,
            serial_number="SER-SECOND",
        )

        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).update_device(
                second.device_id,
                DeviceUpdate(serial_number="SER-EXISTING"),
            )

        assert exc.value.status_code == 409
        assert exc.value.detail == "Serial number already registered"

    def test_update_device_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            DeviceUpdate(status="unknown")

    def test_update_device_rejects_partial_coordinates(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session)
        device = _make_device(db_session, user=user)

        with pytest.raises(ValidationError):
            DeviceUpdate(latitude=-2.0)

        assert device.latitude == pytest.approx(1.0)
        assert device.longitude == pytest.approx(2.0)

    def test_update_device_rejects_mismatched_null_coordinates(self):
        with pytest.raises(ValidationError):
            DeviceUpdate(latitude=None, longitude=29.5)

    def test_update_device_rejects_clearing_coordinates(self):
        with pytest.raises(ValidationError):
            DeviceUpdate(latitude=None, longitude=None)


class TestUpdateDeviceGPS:
    def test_update_gps_updates_coordinates_and_address(
        self,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = _make_user(db_session)
        device = _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-001",
            address="Old address",
        )

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: "New address, Rwanda"),
        )

        updated = DeviceService(db_session).update_device_gps(
            DeviceGPSUpdate(
                serial_number="AQUA-GPS-001",
                latitude=-1.9441,
                longitude=30.0619,
            )
        )

        assert updated.device_id == device.device_id
        assert updated.latitude == pytest.approx(-1.9441)
        assert updated.longitude == pytest.approx(30.0619)
        assert updated.address == "New address, Rwanda"
        assert updated.last_seen_at is not None

    def test_update_gps_preserves_address_if_locationiq_fails(
        self,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = _make_user(db_session)
        _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-002",
            address="Previously saved address",
        )

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: None),
        )

        updated = DeviceService(db_session).update_device_gps(
            DeviceGPSUpdate(
                serial_number="AQUA-GPS-002",
                latitude=-1.95,
                longitude=30.07,
            )
        )

        assert updated.latitude == pytest.approx(-1.95)
        assert updated.longitude == pytest.approx(30.07)
        assert updated.address == "Previously saved address"
        assert updated.last_seen_at is not None

    def test_update_gps_updates_device_without_previous_coordinates(
        self,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
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

        monkeypatch.setattr(
            DeviceService,
            "_get_locationiq_address",
            classmethod(lambda cls, latitude, longitude: "Kigali, Rwanda"),
        )

        updated = DeviceService(db_session).update_device_gps(
            DeviceGPSUpdate(
                serial_number="AQUA-GPS-FIRST",
                latitude=-1.9441,
                longitude=30.0619,
            )
        )

        assert updated.device_id == device.device_id
        assert updated.latitude == pytest.approx(-1.9441)
        assert updated.longitude == pytest.approx(30.0619)
        assert updated.address == "Kigali, Rwanda"
        assert updated.last_seen_at is not None

    def test_update_gps_returns_404_for_unknown_serial(
        self,
        db_session: Session,
    ):
        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).update_device_gps(
                DeviceGPSUpdate(
                    serial_number="UNKNOWN-DEVICE",
                    latitude=-1.9441,
                    longitude=30.0619,
                )
            )

        assert exc.value.status_code == 404
        assert exc.value.detail == "Device not found"

    def test_update_gps_rejects_inactive_device(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session)
        _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-003",
            status=DeviceStatus.INACTIVE,
        )

        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).update_device_gps(
                DeviceGPSUpdate(
                    serial_number="AQUA-GPS-003",
                    latitude=-1.9441,
                    longitude=30.0619,
                )
            )

        assert exc.value.status_code == 409
        assert exc.value.detail == "Only active devices can report GPS coordinates"

    def test_update_gps_rejects_revoked_device(
        self,
        db_session: Session,
    ):
        user = _make_user(db_session)
        _make_device(
            db_session,
            user=user,
            serial_number="AQUA-GPS-004",
            status=DeviceStatus.REVOKED,
            revoked_at=datetime.now(timezone.utc),
        )

        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).update_device_gps(
                DeviceGPSUpdate(
                    serial_number="AQUA-GPS-004",
                    latitude=-1.9441,
                    longitude=30.0619,
                )
            )

        assert exc.value.status_code == 409
        assert exc.value.detail == "Only active devices can report GPS coordinates"


class TestGetAndListDevices:
    def test_get_device_returns_404_when_missing(
        self,
        db_session: Session,
    ):
        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).get_device(uuid4())

        assert exc.value.status_code == 404
        assert exc.value.detail == "Device not found"

    def test_get_device_returns_device(self, db_session: Session):
        user = _make_user(db_session, "device-get@example.com")
        device = _make_device(db_session, user=user)

        result = DeviceService(db_session).get_device(device.device_id)

        assert result.device_id == device.device_id
        assert result.latitude == pytest.approx(1.0)
        assert result.longitude == pytest.approx(2.0)
        assert result.address == "Test address"

    def test_list_devices_empty(self, db_session: Session):
        assert DeviceService(db_session).list_devices() == []

    def test_list_devices_returns_all(self, db_session: Session):
        user = _make_user(db_session, "device-list-all@example.com")
        first = _make_device(db_session, user=user)
        second = _make_device(db_session, user=user)

        result = DeviceService(db_session).list_devices()

        assert {device.device_id for device in result} == {
            first.device_id,
            second.device_id,
        }

    def test_list_devices_filters_by_status(self, db_session: Session):
        user = _make_user(
            db_session,
            "device-list-status@example.com",
        )
        active = _make_device(db_session, user=user)
        inactive = _make_device(
            db_session,
            user=user,
            status=DeviceStatus.INACTIVE,
        )

        active_result = DeviceService(db_session).list_devices(
            status="active",
        )
        inactive_result = DeviceService(db_session).list_devices(
            status="inactive",
        )

        assert [device.device_id for device in active_result] == [active.device_id]
        assert [device.device_id for device in inactive_result] == [inactive.device_id]

    def test_list_devices_rejects_invalid_status(
        self,
        db_session: Session,
    ):
        with pytest.raises(HTTPException) as exc:
            DeviceService(db_session).list_devices(status="unknown")

        assert exc.value.status_code == 422
        assert exc.value.detail == "Invalid device status"

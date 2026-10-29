from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import json
from urllib import parse, request
from urllib.error import HTTPError, URLError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from models.device import Device, DeviceStatus
from models.user import User, UserStatus
from repositories.device import DeviceRepository
from schemas.device import DeviceCreate, DeviceGPSUpdate, DeviceUpdate


class DeviceService:
    def __init__(self, db: Session):
        self.devices = DeviceRepository(db)

    def create_device(
        self,
        data: DeviceCreate,
        current_user: User,
    ) -> Device:
        user = self.devices.get_user_by_id(current_user.user_id)

        if user is None or user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
            )

        if self.devices.get_by_serial(data.serial_number) is not None:
            raise HTTPException(
                status_code=409,
                detail="Serial number already registered",
            )

        device = Device(
            user_id=current_user.user_id,
            serial_number=data.serial_number,
            latitude=data.latitude,
            longitude=data.longitude,
            address=data.address,
            description=data.description,
        )

        if (
            device.latitude is not None
            and device.longitude is not None
            and not device.address
        ):
            self._enrich_device_address(device)

        return self.devices.create(device)

    def update_device_gps(self, data: DeviceGPSUpdate) -> Device:
        device = self.devices.get_by_serial(data.serial_number)

        if device is None:
            raise HTTPException(
                status_code=404,
                detail="Device not found",
            )

        if device.status != DeviceStatus.ACTIVE:
            raise HTTPException(
                status_code=409,
                detail="Only active devices can report GPS coordinates",
            )

        device.latitude = data.latitude
        device.longitude = data.longitude
        device.last_seen_at = datetime.now(timezone.utc)

        address = self._get_locationiq_address(
            data.latitude,
            data.longitude,
        )

        if address:
            device.address = address

        return self.devices.update(device)

    @staticmethod
    def _extract_locationiq_address(
        payload: object,
    ) -> str | None:
        if not isinstance(payload, dict):
            return None

        display_name = payload.get("display_name")

        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()

        address_data = payload.get("address")

        if not isinstance(address_data, dict):
            return None

        parts = []

        for key in (
            "house_number",
            "road",
            "neighbourhood",
            "suburb",
            "city",
            "town",
            "county",
            "state",
            "country",
        ):
            value = address_data.get(key)

            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

        return ", ".join(parts) if parts else None

    @classmethod
    def _get_locationiq_address(
        cls,
        latitude: float,
        longitude: float,
    ) -> str | None:
        api_key = settings.locationiq_api_key

        if not api_key:
            return None

        params = parse.urlencode(
            {
                "key": api_key,
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "zoom": 18,
                "addressdetails": 1,
            }
        )

        url = f"https://us1.locationiq.com/v1/reverse?{params}"

        try:
            with request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
        ):
            return None

        return cls._extract_locationiq_address(payload)

    def _enrich_device_address(self, device: Device) -> Device:
        if device.address or device.latitude is None or device.longitude is None:
            return device

        address = self._get_locationiq_address(
            device.latitude,
            device.longitude,
        )

        if address:
            device.address = address

        return device

    def get_device(self, device_id: UUID) -> Device:
        device = self.devices.get_by_id(device_id)

        if device is None:
            raise HTTPException(
                status_code=404,
                detail="Device not found",
            )

        return device

    def list_devices(
        self,
        status: str | None = None,
    ) -> list[Device]:
        if status is None:
            return self.devices.list_all()

        try:
            device_status = DeviceStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Invalid device status",
            ) from None

        return self.devices.list_all(status=device_status)

    def update_device(
        self,
        device_id: UUID,
        data: DeviceUpdate,
    ) -> Device:
        device = self.devices.get_by_id(device_id)

        if device is None:
            raise HTTPException(
                status_code=404,
                detail="Device not found",
            )

        changes: dict[str, Any] = data.model_dump(exclude_unset=True)

        if "serial_number" in changes:
            serial_number = changes["serial_number"]

            if (
                serial_number is not None
                and serial_number != device.serial_number
                and self.devices.get_by_serial(serial_number) is not None
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Serial number already registered",
                )

        if "status" in changes:
            try:
                new_status = DeviceStatus(changes["status"])
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid device status",
                ) from None

            device.revoked_at = (
                datetime.now(timezone.utc)
                if new_status == DeviceStatus.REVOKED
                else None
            )

            changes["status"] = new_status

        coordinates_changed = "latitude" in changes or "longitude" in changes

        for field, value in changes.items():
            setattr(device, field, value)

        if (
            coordinates_changed
            and "address" not in changes
            and device.latitude is not None
            and device.longitude is not None
        ):
            self._enrich_device_address(device)

        return self.devices.update(device)

    def delete_device(self, device_id: UUID) -> None:
        device = self.devices.get_by_id(device_id)

        if device is None:
            raise HTTPException(
                status_code=404,
                detail="Device not found",
            )

        self.devices.delete_by_id(device_id)

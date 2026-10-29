from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.device import Device, DeviceStatus
from models.user import User


class DeviceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, device: Device) -> Device:
        try:
            self.db.add(device)
            self.db.commit()
            self.db.refresh(device)
            return device
        except Exception:
            self.db.rollback()
            raise

    def get_by_id(self, device_id: UUID) -> Device | None:
        return self.db.get(Device, device_id)

    def get_by_serial(self, serial_number: str) -> Device | None:
        return self.db.scalar(
            select(Device).where(Device.serial_number == serial_number)
        )

    def get_user_by_id(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def list_all(
        self,
        status: DeviceStatus | None = None,
    ) -> list[Device]:
        query = select(Device).order_by(Device.installed_at.desc())

        if status is not None:
            query = query.where(Device.status == status)

        return list(self.db.scalars(query).all())

    def update(self, device: Device) -> Device:
        try:
            self.db.add(device)
            self.db.commit()
            self.db.refresh(device)
            return device
        except Exception:
            self.db.rollback()
            raise

    def delete_by_id(self, device_id: UUID) -> Device | None:
        device = self.get_by_id(device_id)

        if device is None:
            return None

        try:
            self.db.execute(delete(Device).where(Device.device_id == device_id))
            self.db.commit()
            return device
        except Exception:
            self.db.rollback()
            raise

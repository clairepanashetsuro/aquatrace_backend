import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.maintenance_record import (
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceType,
)


class MaintenanceRecordRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _with_names():
        return (
            selectinload(MaintenanceRecord.user),
            selectinload(MaintenanceRecord.device),
        )

    def get(self, maintenance_id: uuid.UUID) -> MaintenanceRecord | None:
        return self.db.get(
            MaintenanceRecord,
            maintenance_id,
            options=self._with_names(),
        )

    def device_exists(self, device_id: uuid.UUID) -> bool:
        device_cls = MaintenanceRecord.device.property.mapper.class_
        return self.db.get(device_cls, device_id) is not None

    def incident_exists(self, incident_id: uuid.UUID) -> bool:
        incident_cls = MaintenanceRecord.incident.property.mapper.class_
        return self.db.get(incident_cls, incident_id) is not None

    def create(self, **data: Any) -> MaintenanceRecord:
        record = MaintenanceRecord(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update(
        self,
        record: MaintenanceRecord,
        changes: dict[str, Any],
    ) -> MaintenanceRecord:
        for field, value in changes.items():
            setattr(record, field, value)

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_user_by_id(self, user_id: uuid.UUID):
        user_cls = MaintenanceRecord.user.property.mapper.class_
        return self.db.get(user_cls, user_id)

    def list(
        self,
        *,
        device_id: uuid.UUID | None = None,
        incident_id: uuid.UUID | None = None,
        performed_by: uuid.UUID | None = None,
        maintenance_type: MaintenanceType | None = None,
        status: MaintenanceStatus | None = None,
        performed_from: datetime | None = None,
        performed_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MaintenanceRecord], int]:
        model = MaintenanceRecord
        conditions = []

        if device_id:
            conditions.append(model.device_id == device_id)
        if incident_id:
            conditions.append(model.incident_id == incident_id)
        if performed_by:
            conditions.append(model.performed_by == performed_by)
        if maintenance_type:
            conditions.append(model.maintenance_type == maintenance_type)
        if status:
            conditions.append(model.status == status)
        if performed_from:
            conditions.append(model.performed_at >= performed_from)
        if performed_to:
            conditions.append(model.performed_at <= performed_to)

        total = self.db.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )

        rows = self.db.scalars(
            select(model)
            .where(*conditions)
            .options(*self._with_names())
            .order_by(
                model.performed_at.desc(),
                model.maintenance_id,
            )
            .limit(limit)
            .offset(offset)
        ).all()

        return list(rows), total or 0

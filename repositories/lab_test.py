import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.lab_test import LabTest


class LabTestRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_id(self, user_id: uuid.UUID):
        user_cls = LabTest.user.property.mapper.class_
        return self.db.get(user_cls, user_id)

    def get_incident(self, incident_id: uuid.UUID):
        incident_cls = LabTest.incident.property.mapper.class_
        return self.db.get(incident_cls, incident_id)

    def incident_exists(self, incident_id: uuid.UUID) -> bool:
        return self.get_incident(incident_id) is not None

    def get(self, lab_test_id: uuid.UUID) -> LabTest | None:
        return self.db.get(
            LabTest,
            lab_test_id,
            options=[selectinload(LabTest.user)],
        )

    def create(self, **data: Any) -> LabTest:
        record = LabTest(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        self.db.refresh(record, ["user"])
        return record

    def update(self, record: LabTest, changes: dict[str, Any]) -> LabTest:
        for field, value in changes.items():
            setattr(record, field, value)

        self.db.commit()
        self.db.refresh(record)
        self.db.refresh(record, ["user"])
        return record

    def list(
        self,
        *,
        incident_id: uuid.UUID | None = None,
        recorded_by: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        parameter: str | None = None,
        laboratory_name: str | None = None,
        sampled_from: datetime | None = None,
        sampled_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[LabTest], int]:
        model = LabTest
        conditions = []

        if incident_id:
            conditions.append(model.incident_id == incident_id)

        if recorded_by:
            conditions.append(model.recorded_by == recorded_by)

        if assigned_to:
            incident_cls = model.incident.property.mapper.class_
            assigned_incidents = select(incident_cls.incident_id).where(
                incident_cls.assigned_to == assigned_to
            )
            conditions.append(model.incident_id.in_(assigned_incidents))

        if parameter:
            conditions.append(func.lower(model.parameter) == parameter.strip().lower())

        if laboratory_name:
            conditions.append(
                model.laboratory_name.icontains(
                    laboratory_name.strip(),
                    autoescape=True,
                )
            )

        if sampled_from:
            conditions.append(model.sample_collected_at >= sampled_from)

        if sampled_to:
            conditions.append(model.sample_collected_at <= sampled_to)

        total = self.db.scalar(
            select(func.count()).select_from(model).where(*conditions)
        )

        rows = self.db.scalars(
            select(model)
            .options(selectinload(model.user))
            .where(*conditions)
            .order_by(model.sample_collected_at.desc(), model.lab_test_id)
            .limit(limit)
            .offset(offset)
        ).all()

        return list(rows), total or 0

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.incident import Incident


Alert = Incident.alert.property.mapper.class_
User = Incident.assigned_user.property.mapper.class_


class IncidentRepository:
    def __init__(self, db: Session):
        self.db = db

    def _with_people(self):
        return (
            selectinload(Incident.assigned_user),
            selectinload(Incident.resolved_user),
        )

    def get(self, incident_id: UUID) -> Optional[Incident]:
        stmt = (
            select(Incident)
            .where(Incident.incident_id == incident_id)
            .options(*self._with_people())
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_alert(self, alert_id: UUID):
        return self.db.get(Alert, alert_id)

    def get_user_by_id(self, user_id: UUID):
        return self.db.get(User, user_id)

    def incident_exists_for_alert(self, alert_id: UUID) -> bool:
        stmt = select(Incident.incident_id).where(Incident.alert_id == alert_id)
        return self.db.execute(stmt).first() is not None

    def create(self, data: Dict[str, Any]) -> Incident:
        incident = Incident(**data)
        self.db.add(incident)
        self.db.commit()
        return self.get(incident.incident_id)

    def update(self, incident: Incident, data: Dict[str, Any]) -> Incident:
        for key, value in data.items():
            setattr(incident, key, value)
        self.db.commit()
        return self.get(incident.incident_id)

    def list(
        self,
        limit: int,
        offset: int,
        status=None,
        priority=None,
        assigned_to: Optional[UUID] = None,
        alert_id: Optional[UUID] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> Tuple[List[Incident], int]:
        conditions = []
        if status:
            conditions.append(Incident.status == status)
        if priority:
            conditions.append(Incident.priority == priority)
        if assigned_to:
            conditions.append(Incident.assigned_to == assigned_to)
        if alert_id:
            conditions.append(Incident.alert_id == alert_id)
        if created_from:
            conditions.append(Incident.created_at >= created_from)
        if created_to:
            conditions.append(Incident.created_at <= created_to)

        total = self.db.execute(
            select(func.count()).select_from(Incident).where(*conditions)
        ).scalar_one()
        stmt = (
            select(Incident)
            .where(*conditions)
            .options(*self._with_people())
            .order_by(Incident.created_at.desc(), Incident.incident_id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars().all()), total

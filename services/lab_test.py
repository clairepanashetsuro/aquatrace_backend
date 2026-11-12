import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.error import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from repositories.lab_test import LabTestRepository
from schemas.lab_test import LabTestCreate, LabTestUpdate

FIELD_ROLE = "field_officer"
WQO_ROLE = "water_quality_officer"
ADMIN_ROLE = "admin"

READ_ROLES = {FIELD_ROLE, WQO_ROLE, ADMIN_ROLE}
WRITE_ROLES = {FIELD_ROLE, ADMIN_ROLE}
MAX_LIMIT = 100

REQUIRED_FIELDS = (
    "laboratory_name",
    "parameter",
    "result_value",
    "unit",
    "sample_collected_at",
)


def get_role_name(user) -> str:
    raw = str(getattr(user.role, "value", user.role))
    return raw.strip().lower().replace(" ", "_")


def ensure_can_read(user) -> None:
    if get_role_name(user) not in READ_ROLES:
        raise PermissionDeniedError(
            "Only Field Officers, Water Quality Officers, and admins "
            "can access lab tests."
        )


def ensure_can_write(user) -> None:
    if get_role_name(user) not in WRITE_ROLES:
        raise PermissionDeniedError(
            "Only Field Officers and admins can create or update lab tests."
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _check_dates(sample_collected_at, tested_at) -> None:
    if tested_at is not None and _aware(tested_at) < _aware(sample_collected_at):
        raise BusinessRuleError("tested_at cannot be earlier than sample_collected_at.")


class LabTestService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = LabTestRepository(db)

    def _require_incident_access(self, incident_id: uuid.UUID, current_user):
        incident = self.repo.get_incident(incident_id)

        if incident is None:
            raise NotFoundError("Incident not found.")

        if (
            get_role_name(current_user) == FIELD_ROLE
            and incident.assigned_to != current_user.user_id
        ):
            raise PermissionDeniedError(
                "You can only access lab tests for incidents assigned to you."
            )

        return incident

    def create(self, payload: LabTestCreate, current_user):
        ensure_can_write(current_user)
        self._require_incident_access(payload.incident_id, current_user)
        _check_dates(payload.sample_collected_at, payload.tested_at)

        return self.repo.create(
            **payload.model_dump(),
            recorded_by=current_user.user_id,
        )

    def get(self, lab_test_id: uuid.UUID, current_user):
        ensure_can_read(current_user)

        record = self.repo.get(lab_test_id)
        if record is None:
            raise NotFoundError("Lab test not found.")

        self._require_incident_access(record.incident_id, current_user)
        return record

    def list(
        self,
        current_user,
        *,
        limit: int = 20,
        offset: int = 0,
        **filters,
    ):
        ensure_can_read(current_user)

        if not 1 <= limit <= MAX_LIMIT:
            raise BusinessRuleError(f"limit must be between 1 and {MAX_LIMIT}.")
        if offset < 0:
            raise BusinessRuleError("offset must be 0 or more.")

        if get_role_name(current_user) == FIELD_ROLE:
            filters["assigned_to"] = current_user.user_id
        else:
            filters.pop("assigned_to", None)

        return self.repo.list(
            limit=limit,
            offset=offset,
            **filters,
        )

    def update(
        self,
        lab_test_id: uuid.UUID,
        payload: LabTestUpdate,
        current_user,
    ):
        ensure_can_write(current_user)
        record = self.get(lab_test_id, current_user)

        if (
            get_role_name(current_user) != ADMIN_ROLE
            and record.recorded_by != current_user.user_id
        ):
            raise PermissionDeniedError(
                "You can only edit lab results that you recorded."
            )

        changes = payload.model_dump(exclude_unset=True)

        for field in REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise BusinessRuleError(f"{field} cannot be null.")

        if changes.get("incident_id") is not None:
            self._require_incident_access(changes["incident_id"], current_user)

        _check_dates(
            changes.get("sample_collected_at", record.sample_collected_at),
            changes.get("tested_at", record.tested_at),
        )

        return self.repo.update(record, changes)

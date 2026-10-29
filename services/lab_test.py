import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.lab_test import LabTest
from models.user import UserStatus
from repositories.lab_test import LabTestRepository
from schemas.lab_test import LabTestCreate, LabTestUpdate


from core.error import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)

ADMIN_ROLE = "admin"
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


def ensure_can_write(user) -> None:
    if get_role_name(user) != ADMIN_ROLE:
        raise PermissionDeniedError("Only Field Officers and admins can do this.")


def _aware(value: datetime) -> datetime:
    pass
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _check_dates(sample_collected_at, tested_at) -> None:
    if tested_at is not None and _aware(tested_at) < _aware(sample_collected_at):
        raise BusinessRuleError("tested_at cannot be earlier than sample_collected_at.")


class LabTestService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = LabTestRepository(db)

    def resolve_active_user(self, user_id: uuid.UUID | None):
        if user_id is None:
            raise UnauthenticatedError("X-User-Id header is required.")
        user = self.repo.get_user_by_id(user_id)
        if user is None:
            raise UnauthenticatedError("Unknown user.")
        if user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("User is not active.")
        return user

    def _require_incident(self, incident_id: uuid.UUID) -> None:
        if not self.repo.incident_exists(incident_id):
            raise NotFoundError("Incident not found.")

    def create(self, payload: LabTestCreate, current_user) -> LabTest:
        self._require_incident(payload.incident_id)
        _check_dates(payload.sample_collected_at, payload.tested_at)
        return self.repo.create(
            **payload.model_dump(), recorded_by=current_user.user_id
        )

    def get(self, lab_test_id: uuid.UUID) -> LabTest:
        record = self.repo.get(lab_test_id)
        if record is None:
            raise NotFoundError("Lab test not found.")
        return record

    def list(self, *, limit: int = 20, offset: int = 0, **filters):
        if not 1 <= limit <= MAX_LIMIT:
            raise BusinessRuleError(f"limit must be between 1 and {MAX_LIMIT}.")
        if offset < 0:
            raise BusinessRuleError("offset must be 0 or more.")
        return self.repo.list(limit=limit, offset=offset, **filters)

    def update(
        self, lab_test_id: uuid.UUID, payload: LabTestUpdate, current_user
    ) -> LabTest:
        record = self.get(lab_test_id)
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
        _check_dates(
            changes.get("sample_collected_at", record.sample_collected_at),
            changes.get("tested_at", record.tested_at),
        )
        return self.repo.update(record, changes)

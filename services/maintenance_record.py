import uuid

from sqlalchemy.orm import Session

from core.error import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)
from models.maintenance_record import MaintenanceRecord, MaintenanceStatus
from models.user import UserStatus
from repositories.maintenance_record import MaintenanceRecordRepository
from schemas.maintenance_record import (
    MaintenanceRecordCreate,
    MaintenanceRecordUpdate,
)

ADMIN_ROLE = "admin"
WRITE_ROLES = {"field_officer", "admin"}
MAX_LIMIT = 100


def get_role_name(user) -> str:
    raw = str(getattr(user.role, "value", user.role))
    return raw.strip().lower().replace(" ", "_")


def ensure_can_write(user) -> None:
    if get_role_name(user) not in WRITE_ROLES:
        raise PermissionDeniedError("Only Field Officers and admins can do this.")


def _check_business_rules(status, next_scheduled_date, pre_value, post_value) -> None:
    if status == MaintenanceStatus.SCHEDULED:
        if next_scheduled_date is None:
            raise BusinessRuleError(
                "next_scheduled_date is required when status is 'scheduled'."
            )
        if pre_value is not None or post_value is not None:
            raise BusinessRuleError(
                "Readings cannot be logged on a record that is only scheduled."
            )


class MaintenanceRecordService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = MaintenanceRecordRepository(db)

    def resolve_active_user(self, user_id: uuid.UUID | None):
        if user_id is None:
            raise UnauthenticatedError("X-User-Id header is required.")
        user = self.repo.get_user_by_id(user_id)
        if user is None:
            raise UnauthenticatedError("Unknown user.")
        if user.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("User is not active.")
        return user

    def _require_device(self, device_id: uuid.UUID) -> None:
        if not self.repo.device_exists(device_id):
            raise NotFoundError("Device not found.")

    def _require_incident(self, incident_id: uuid.UUID) -> None:
        if not self.repo.incident_exists(incident_id):
            raise NotFoundError("Incident not found.")

    def _get_or_404(self, maintenance_id: uuid.UUID) -> MaintenanceRecord:
        record = self.repo.get(maintenance_id)
        if record is None:
            raise NotFoundError("Maintenance record not found.")
        return record

    def create(
        self, payload: MaintenanceRecordCreate, current_user
    ) -> MaintenanceRecord:
        self._require_device(payload.device_id)
        if payload.incident_id:
            self._require_incident(payload.incident_id)
        _check_business_rules(
            payload.status,
            payload.next_scheduled_date,
            payload.pre_maintenance_value,
            payload.post_maintenance_value,
        )
        return self.repo.create(
            **payload.model_dump(), performed_by=current_user.user_id
        )

    def get(self, maintenance_id: uuid.UUID) -> MaintenanceRecord:
        return self._get_or_404(maintenance_id)

    def list(self, *, limit: int = 20, offset: int = 0, **filters):
        if not 1 <= limit <= MAX_LIMIT:
            raise BusinessRuleError(f"limit must be between 1 and {MAX_LIMIT}.")
        if offset < 0:
            raise BusinessRuleError("offset must be 0 or more.")
        return self.repo.list(limit=limit, offset=offset, **filters)

    def update(
        self, maintenance_id: uuid.UUID, payload: MaintenanceRecordUpdate, current_user
    ):
        record = self._get_or_404(maintenance_id)

        if (
            get_role_name(current_user) != ADMIN_ROLE
            and record.performed_by != current_user.user_id
        ):
            raise PermissionDeniedError(
                "You can only edit maintenance records you created."
            )

        changes = payload.model_dump(exclude_unset=True)
        for required in ("maintenance_type", "performed_at", "status"):
            if required in changes and changes[required] is None:
                raise BusinessRuleError(f"{required} cannot be null.")
        if changes.get("incident_id"):
            self._require_incident(changes["incident_id"])

        _check_business_rules(
            changes.get("status", record.status),
            changes.get("next_scheduled_date", record.next_scheduled_date),
            changes.get("pre_maintenance_value", record.pre_maintenance_value),
            changes.get("post_maintenance_value", record.post_maintenance_value),
        )
        return self.repo.update(record, changes)

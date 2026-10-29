from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from core.error import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    UnauthenticatedError,
)
from models.incident import IncidentStatus
from repositories.incident import IncidentRepository


def get_role_name(role) -> str:

    return str(getattr(role, "value", role)).strip().lower().replace(" ", "_")


MAX_LIMIT = 100
MAX_NOTE_LENGTH = 5000
MANAGER_ROLES = {"water_quality_officer", "admin"}
FIELD_ROLE = "field_officer"
ADMIN_ROLE = "admin"


def _is_active(user) -> bool:
    status = getattr(user.status, "value", user.status)
    return str(status).strip().lower() == "active"


class IncidentService:
    def __init__(self, repo: IncidentRepository):
        self.repo = repo

    def resolve_active_user(self, user_id: Optional[UUID]):
        if user_id is None:
            raise UnauthenticatedError("Send your user id in the X-User-Id header.")
        user = self.repo.get_user_by_id(user_id)
        if user is None or not _is_active(user):
            raise UnauthenticatedError("User not found or not active.")
        return user

    def _role(self, user) -> str:
        return get_role_name(user.role)

    def _require_manager(self, user, action: str) -> None:
        if self._role(user) not in MANAGER_ROLES:
            raise PermissionDeniedError(
                f"Only a Water Quality Officer or Admin can {action}."
            )

    def _can_work_on(self, user, incident) -> bool:
        if self._role(user) == ADMIN_ROLE:
            return True
        return self._role(user) == FIELD_ROLE and incident.assigned_to == user.user_id

    def _load(self, incident_id: UUID):
        incident = self.repo.get(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found.")
        return incident

    def _require_assignable(self, user_id: UUID):
        user = self.repo.get_user_by_id(user_id)
        if user is None:
            raise NotFoundError("Assignee not found.")
        if self._role(user) != FIELD_ROLE or not _is_active(user):
            raise BusinessRuleError(
                "Incidents can only be assigned to an active Field Officer."
            )
        return user

    @staticmethod
    def _require_not_closed(incident) -> None:
        if incident.status == IncidentStatus.CLOSED:
            raise BusinessRuleError("A closed incident cannot be changed.")

    def create(self, caller, payload: Dict[str, Any]):
        self._require_manager(caller, "create incidents")
        if self.repo.get_alert(payload["alert_id"]) is None:
            raise NotFoundError("Alert not found.")
        if self.repo.incident_exists_for_alert(payload["alert_id"]):
            raise BusinessRuleError("This alert already has an incident.")

        data = {
            "alert_id": payload["alert_id"],
            "priority": payload["priority"],
            "status": IncidentStatus.OPEN,
        }
        if payload.get("assigned_to"):
            self._require_assignable(payload["assigned_to"])
            data["assigned_to"] = payload["assigned_to"]
            data["status"] = IncidentStatus.INVESTIGATING
        return self.repo.create(data)

    def get(self, caller, incident_id: UUID):
        incident = self._load(incident_id)
        if self._role(caller) == FIELD_ROLE and incident.assigned_to != caller.user_id:
            raise PermissionDeniedError("You can only view incidents assigned to you.")
        return incident

    def list(
        self,
        caller,
        limit: int = 20,
        offset: int = 0,
        status=None,
        priority=None,
        assigned_to: Optional[UUID] = None,
        alert_id: Optional[UUID] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ):
        if limit < 1 or limit > MAX_LIMIT:
            raise BusinessRuleError(f"limit must be between 1 and {MAX_LIMIT}.")
        if offset < 0:
            raise BusinessRuleError("offset cannot be negative.")
        if created_from and created_to and created_from > created_to:
            raise BusinessRuleError("created_from cannot be after created_to.")
        if self._role(caller) == FIELD_ROLE:
            assigned_to = caller.user_id
        return self.repo.list(
            limit,
            offset,
            status,
            priority,
            assigned_to,
            alert_id,
            created_from,
            created_to,
        )

    def update(self, caller, incident_id: UUID, changes: Dict[str, Any]):
        incident = self._load(incident_id)
        self._require_not_closed(incident)
        if (
            not self._can_work_on(caller, incident)
            and self._role(caller) not in MANAGER_ROLES
        ):
            raise PermissionDeniedError("You cannot edit this incident.")

        if "priority" in changes:
            self._require_manager(caller, "change the priority")
            if changes["priority"] is None:
                raise BusinessRuleError("priority cannot be empty.")
        notes_changed = {"findings", "corrective_action", "visited_at"} & changes.keys()
        if notes_changed:
            if not self._can_work_on(caller, incident):
                raise PermissionDeniedError(
                    "Only the assigned Field Officer or an Admin can write field notes."
                )
            if incident.status != IncidentStatus.INVESTIGATING:
                raise BusinessRuleError(
                    "Field notes can only be edited while investigating."
                )
        for name in ("findings", "corrective_action"):
            text = changes.get(name)
            if text is not None and len(text) > MAX_NOTE_LENGTH:
                raise BusinessRuleError(
                    f"{name} cannot be longer than {MAX_NOTE_LENGTH} characters."
                )
        visited = changes.get("visited_at")
        if visited is not None:
            if visited.tzinfo is None:
                visited = visited.replace(tzinfo=timezone.utc)
                changes["visited_at"] = visited
            if visited > datetime.now(timezone.utc):
                raise BusinessRuleError("visited_at cannot be in the future.")
        return self.repo.update(incident, changes)

    def assign(self, caller, incident_id: UUID, assignee_id: UUID):
        self._require_manager(caller, "assign incidents")
        incident = self._load(incident_id)
        self._require_not_closed(incident)
        if incident.status == IncidentStatus.AWAITING_VERIFICATION:
            raise BusinessRuleError(
                "Send the incident back to investigating before reassigning."
            )
        self._require_assignable(assignee_id)
        changes: Dict[str, Any] = {"assigned_to": assignee_id}
        if incident.status == IncidentStatus.OPEN:
            changes["status"] = IncidentStatus.INVESTIGATING
        return self.repo.update(incident, changes)

    def submit(self, caller, incident_id: UUID):
        incident = self._load(incident_id)
        if not self._can_work_on(caller, incident):
            raise PermissionDeniedError(
                "Only the assigned Field Officer or an Admin can submit for verification."
            )
        if incident.status != IncidentStatus.INVESTIGATING:
            raise BusinessRuleError(
                "Only an incident being investigated can be submitted."
            )
        missing = [
            name
            for name in ("findings", "corrective_action", "visited_at")
            if not getattr(incident, name)
        ]
        if missing:
            raise BusinessRuleError(
                "Complete these field notes first: " + ", ".join(missing) + "."
            )
        return self.repo.update(
            incident, {"status": IncidentStatus.AWAITING_VERIFICATION}
        )

    def reopen(self, caller, incident_id: UUID):
        self._require_manager(caller, "send an incident back")
        incident = self._load(incident_id)
        if incident.status != IncidentStatus.AWAITING_VERIFICATION:
            raise BusinessRuleError(
                "Only an incident awaiting verification can be sent back."
            )
        return self.repo.update(incident, {"status": IncidentStatus.INVESTIGATING})

    def close(self, caller, incident_id: UUID):
        self._require_manager(caller, "close incidents")
        incident = self._load(incident_id)
        if incident.status != IncidentStatus.AWAITING_VERIFICATION:
            raise BusinessRuleError(
                "Only an incident awaiting verification can be closed."
            )
        return self.repo.update(
            incident,
            {
                "status": IncidentStatus.CLOSED,
                "resolved_by": caller.user_id,
                "closed_at": datetime.now(timezone.utc),
            },
        )

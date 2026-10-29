from uuid import UUID
from sqlalchemy.orm import Session
from models.audit_log import AuditLog
from repositories.audit_log_repository import AuditLogRepository
from core.exceptions import ResourceNotFoundError


class AuditService:
    def __init__(self, db: Session):
        self.audit_logs = AuditLogRepository(db)

    def record_event(
        self,
        action: str,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        ip_address: str | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        if not action or not action.strip():
            raise ValueError("Audit action cannot be empty")

        audit_log = AuditLog(
            user_id=user_id,
            action=action.strip(),
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            details=details,
        )
        return self.audit_logs.add(audit_log)

    def get_event(self, audit_log_id: UUID) -> AuditLog | None:
        return self.audit_logs.get_by_id(audit_log_id)

    def get_event_or_raise(self, audit_log_id: UUID) -> AuditLog:
        event = self.get_event(audit_log_id)

        if event is None:
            raise ResourceNotFoundError("Audit log entry not found")

        return event

    def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        self._validate_pagination(limit, offset)
        return self.audit_logs.list_logs(limit=limit, offset=offset)

    def list_events_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        self._validate_pagination(limit, offset)
        return self.audit_logs.list_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    def list_events_by_action(
        self,
        action: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        if not action or not action.strip():
            raise ValueError("Audit action cannot be empty")
        self._validate_pagination(limit, offset)
        return self.audit_logs.list_by_action(
            action=action.strip(),
            limit=limit,
            offset=offset,
        )

    def list_events_page(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: UUID | None = None,
        action: str | None = None,
    ) -> dict:
        self._validate_pagination(limit, offset)

        if action is not None:
            action = action.strip()
            if not action:
                raise ValueError("Audit action cannot be empty")

        if user_id is not None and action is not None:
            items = self.audit_logs.list_by_user_and_action(
                user_id=user_id,
                action=action,
                limit=limit,
                offset=offset,
            )
            total = self.audit_logs.count_by_user_and_action(
                user_id=user_id,
                action=action,
            )
        elif user_id is not None:
            items = self.audit_logs.list_by_user(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
            total = self.audit_logs.count_by_user(user_id=user_id)
        elif action is not None:
            items = self.audit_logs.list_by_action(
                action=action,
                limit=limit,
                offset=offset,
            )
            total = self.audit_logs.count_by_action(action=action)
        else:
            items = self.audit_logs.list_logs(limit=limit, offset=offset)
            total = self.audit_logs.count_logs()

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    def _validate_pagination(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("Offset cannot be negative")

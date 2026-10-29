from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_admin
from models.audit_log import AuditLog
from models.user import User
from schemas.audit_log import AuditLogPage, AuditLogRead
from services.audit_service import AuditService


router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID | None = Query(default=None),
    action: str | None = Query(default=None, min_length=1, max_length=50),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AuditService(db).list_events_page(
        limit=limit,
        offset=offset,
        user_id=user_id,
        action=action,
    )


@router.get("/{audit_log_id}", response_model=AuditLogRead)
def get_audit_log(
    audit_log_id: UUID,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuditLog:
    return AuditService(db).get_event_or_raise(audit_log_id)

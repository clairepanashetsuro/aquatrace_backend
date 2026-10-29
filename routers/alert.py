from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.alert import AlertStatus, SeverityLevel
from schemas.alert import AlertResponse, AlertResolveUpdate, AlertSeenUpdate
from schemas.rag import RAGAlertExplanation
from services import alert_service, rag_service
from dependencies import require_water_quality_officer

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_water_quality_officer)],
)


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    status: AlertStatus | None = None,
    severity: SeverityLevel | None = None,
    device_id: UUID | None = None,
    seen: bool | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return alert_service.list_alerts(
        db, status, severity, device_id, search, limit, offset, seen
    )


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: UUID, db: Session = Depends(get_db)):
    return alert_service.get_alert(db, alert_id)


@router.post("/{alert_id}/explanation", response_model=RAGAlertExplanation)
def explain_alert(alert_id: UUID, db: Session = Depends(get_db)):
    return rag_service.generate_alert_explanation(db, alert_id)


@router.patch("/{alert_id}/seen", response_model=AlertResponse)
def mark_alert_seen(
    alert_id: UUID,
    payload: AlertSeenUpdate,
    db: Session = Depends(get_db),
):
    return alert_service.mark_alert_seen(db, alert_id, payload)


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveUpdate,
    db: Session = Depends(get_db),
):
    return alert_service.resolve_alert(db, alert_id, payload)

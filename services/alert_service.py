from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus, SeverityLevel
from repositories import alert_repository
from schemas.alert import AlertSeenUpdate, AlertResolveUpdate
from services import alert_rules


def process_new_reading(db: Session, reading_id: UUID) -> None:
    reading = alert_repository.get_sensor_reading(db, reading_id)

    if reading is not None:
        alert_rules.evaluate_reading(db, reading)


def list_alerts(
    db: Session,
    status: AlertStatus | None,
    severity: SeverityLevel | None,
    device_id: UUID | None,
    search: str | None,
    limit: int,
    offset: int,
    seen: bool | None = None,
) -> list[Alert]:
    return alert_repository.list_alerts(
        db,
        status=status,
        severity=severity,
        device_id=device_id,
        search=search,
        limit=limit,
        offset=offset,
        seen=seen,
    )


def get_alert(db: Session, alert_id: UUID) -> Alert:
    alert = alert_repository.get_alert(db, alert_id)

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found",
        )

    return alert


def mark_alert_seen(
    db: Session,
    alert_id: UUID,
    payload: AlertSeenUpdate,
) -> Alert:
    if not payload.seen:
        raise HTTPException(
            status_code=422,
            detail="The seen field must be true",
        )

    alert = get_alert(db, alert_id)

    if alert.seen_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Alert has already been seen",
        )

    return alert_repository.mark_seen(db, alert)


def resolve_alert(
    db: Session,
    alert_id: UUID,
    payload: AlertResolveUpdate,
) -> Alert:
    if payload.status != AlertStatus.RESOLVED:
        raise HTTPException(
            status_code=422,
            detail="Only the resolved status is supported",
        )

    alert = get_alert(db, alert_id)

    if alert.status == AlertStatus.RESOLVED:
        raise HTTPException(
            status_code=409,
            detail="Alert is already resolved",
        )

    return alert_repository.set_status(
        db,
        alert,
        AlertStatus.RESOLVED,
    )


def add_occurrence(
    db: Session,
    alert: Alert,
    observed: float | None,
    limit: float | None,
    severity: SeverityLevel,
) -> Alert:
    alert.occurrence_count += 1

    if observed is not None:
        alert.observed_value = observed

    if limit is not None:
        alert.threshold_value = limit

    alert.severity = severity

    return alert_repository.save_alert(db, alert)

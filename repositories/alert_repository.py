from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.alert import Alert, AlertStatus, AlertType, SeverityLevel
from models.device import Device
from models.sensor_reading import SensorReading, SensorStatus
from models.user import User, UserRole


def create_alert(db: Session, data: dict) -> Alert:
    alert = Alert(**data)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_alert(db: Session, alert_id: UUID) -> Alert | None:
    return db.get(Alert, alert_id)


def get_sensor_reading(db: Session, reading_id: UUID) -> SensorReading | None:
    return db.get(SensorReading, reading_id)


def find_open_alert(db: Session, device_id: UUID, parameter: str) -> Alert | None:
    return (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.parameter == parameter,
            Alert.alert_type == AlertType.THRESHOLD_BREACH,
            Alert.status != AlertStatus.RESOLVED,
        )
        .first()
    )


def recent_readings(
    db: Session,
    device_id: UUID,
    up_to: datetime,
    limit: int,
) -> list[SensorReading]:
    return (
        db.query(SensorReading)
        .filter(
            SensorReading.device_id == device_id,
            SensorReading.sensor_status == SensorStatus.OK,
            SensorReading.recorded_at <= up_to,
        )
        .order_by(SensorReading.recorded_at.desc())
        .limit(limit)
        .all()
    )


def save_alert(db: Session, alert: Alert) -> Alert:
    db.commit()
    db.refresh(alert)
    return alert


def list_alerts(
    db: Session,
    *,
    status: AlertStatus | None,
    severity: SeverityLevel | None,
    device_id: UUID | None,
    search: str | None,
    limit: int,
    offset: int,
    seen: bool | None = None,
) -> list[Alert]:
    query = db.query(Alert).join(Alert.device)

    if status is not None:
        query = query.filter(Alert.status == status)

    if severity is not None:
        query = query.filter(Alert.severity == severity)

    if device_id is not None:
        query = query.filter(Alert.device_id == device_id)

    if seen is True:
        query = query.filter(Alert.seen_at.is_not(None))
    elif seen is False:
        query = query.filter(Alert.seen_at.is_(None))

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Alert.message.ilike(pattern),
                Device.serial_number.ilike(pattern),
                Device.address.ilike(pattern),
            )
        )

    return query.order_by(Alert.created_at.desc()).offset(offset).limit(limit).all()


def set_status(
    db: Session,
    alert: Alert,
    status: AlertStatus,
) -> Alert:
    alert.status = status
    db.commit()
    db.refresh(alert)
    return alert


def mark_seen(db: Session, alert: Alert) -> Alert:
    alert.seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert


def unnotified_critical(db: Session, device_id: UUID) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(
            Alert.device_id == device_id,
            Alert.severity == SeverityLevel.CRITICAL,
            Alert.status == AlertStatus.TRIGGERED,
            Alert.seen_at.is_(None),
            Alert.officers_notified_at.is_(None),
        )
        .all()
    )


def officer_emails(db: Session) -> list[str]:
    rows = (
        db.query(User.email).filter(User.role == UserRole.WATER_QUALITY_OFFICER).all()
    )
    return [row.email for row in rows]


def mark_officers_notified(db: Session, alert: Alert) -> Alert:
    alert.officers_notified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert

from sqlalchemy.orm import Session

from core.thresholds import (
    CONSECUTIVE_READINGS,
    LIMITS,
    breach_distance,
    breach_message,
    crossed_limit,
)
from models.alert import Alert, AlertType, SeverityLevel
from models.sensor_reading import SensorReading, SensorStatus
from repositories import alert_repository
from services import alert_service


def is_sustained_breach(
    db: Session,
    reading: SensorReading,
    parameter: str,
) -> bool:
    latest = alert_repository.recent_readings(
        db,
        reading.device_id,
        reading.recorded_at,
        CONSECUTIVE_READINGS,
    )

    if len(latest) < CONSECUTIVE_READINGS:
        return False

    return all(
        crossed_limit(parameter, getattr(item, parameter)) is not None
        for item in latest
    )


def breached_parameters(
    db: Session,
    reading: SensorReading,
) -> list[str]:
    if reading.sensor_status == SensorStatus.FAULT:
        return []

    return [
        parameter for parameter in LIMITS if is_sustained_breach(db, reading, parameter)
    ]


def evaluate_reading(
    db: Session,
    reading: SensorReading,
) -> list[Alert]:
    breached = breached_parameters(db, reading)

    if not breached:
        return []

    severity = SeverityLevel.CRITICAL if len(breached) >= 2 else SeverityLevel.WARNING

    new_alerts = []

    for parameter in breached:
        value = getattr(reading, parameter)
        limit = crossed_limit(parameter, value)

        alert = alert_repository.find_open_alert(
            db,
            reading.device_id,
            parameter,
        )

        if alert is None:
            alert = alert_repository.create_alert(
                db,
                {
                    "device_id": reading.device_id,
                    "reading_id": reading.reading_id,
                    "alert_type": AlertType.THRESHOLD_BREACH,
                    "parameter": parameter,
                    "observed_value": value,
                    "threshold_value": limit,
                    "severity": severity,
                    "message": breach_message(parameter, value),
                },
            )
            new_alerts.append(alert)
            continue

        previous_distance = (
            None
            if alert.observed_value is None
            else breach_distance(parameter, alert.observed_value)
        )
        current_distance = breach_distance(parameter, value)
        worse = previous_distance is None or current_distance > previous_distance

        escalated = (
            alert.severity == SeverityLevel.WARNING
            and severity == SeverityLevel.CRITICAL
        )

        alert_service.add_occurrence(
            db,
            alert,
            value if worse else None,
            limit,
            (SeverityLevel.CRITICAL if escalated else alert.severity),
        )

    return new_alerts

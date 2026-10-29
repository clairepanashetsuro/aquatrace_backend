from uuid import UUID
from sqlalchemy.orm import Session
from models.sensor_reading import SensorReading


def get_reading_by_device_and_message(
    db: Session, device_id: UUID, message_number: int
) -> SensorReading | None:
    """Used for deduplication. Checks if this message already exists for this device."""
    return (
        db.query(SensorReading)
        .filter(
            SensorReading.device_id == device_id,
            SensorReading.message_number == message_number,
        )
        .first()
    )


def create_reading(db: Session, reading_data: dict) -> SensorReading:
    reading = SensorReading(**reading_data)
    db.add(reading)
    db.flush()
    return reading


def get_readings(
    db: Session, device_id: UUID | None = None, limit: int = 100
) -> list[SensorReading]:
    query = db.query(SensorReading)
    if device_id is not None:
        query = query.filter(SensorReading.device_id == device_id)
    return (
        query.order_by(
            SensorReading.recorded_at.desc(), SensorReading.created_at.desc()
        )
        .limit(limit)
        .all()
    )


def get_reading_by_id(db: Session, reading_id: UUID) -> SensorReading | None:
    return (
        db.query(SensorReading).filter(SensorReading.reading_id == reading_id).first()
    )


def get_latest_reading_per_device(db: Session) -> list[SensorReading]:
    latest_readings = (
        db.query(SensorReading.reading_id.label("reading_id"))
        .distinct(SensorReading.device_id)
        .order_by(
            SensorReading.device_id,
            SensorReading.recorded_at.desc(),
            SensorReading.created_at.desc(),
        )
        .subquery()
    )
    return (
        db.query(SensorReading)
        .join(latest_readings, SensorReading.reading_id == latest_readings.c.reading_id)
        .all()
    )


def get_readings_by_device(
    db: Session, device_id: UUID, limit: int = 100
) -> list[SensorReading]:
    return (
        db.query(SensorReading)
        .filter(SensorReading.device_id == device_id)
        .order_by(SensorReading.recorded_at.desc())
        .limit(limit)
        .all()
    )

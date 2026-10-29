
import math
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.sensor_reading import SensorReading, SensorStatus, WqiStatus
from models.wqi_weight import WqiWeight
from models.device import Device
from schemas.sensor_reading import SensorReadingCreate
from repositories.sensor_reading_repository import (
    get_reading_by_device_and_message,
    create_reading,
    get_readings,
    get_reading_by_id,
    get_latest_reading_per_device,
    get_readings_by_device,
)
from services import alert_service


PARAMETERS = {
    "ph",
    "temperature",
    "turbidity",
    "electrical_conductivity",
}


def normalize_temperature(temp: float) -> float:
    if not math.isfinite(temp):
        raise ValueError("Temperature must be finite.")
    if 20.0 <= temp <= 25.0:
        return 100.0
    if 15.0 <= temp < 20.0:
        return ((temp - 15.0) / 5.0) * 100.0
    if 25.0 < temp <= 30.0:
        return ((30.0 - temp) / 5.0) * 100.0
    return 0.0


def normalize_ph(ph: float) -> float:
    if not math.isfinite(ph) or not 0.0 <= ph <= 14.0:
        raise ValueError("pH must be a finite value between 0 and 14.")
    if 6.5 <= ph <= 8.5:
        return 100.0
    if 5.5 <= ph < 6.5:
        return (ph - 5.5) * 100.0
    if 8.5 < ph <= 9.5:
        return (9.5 - ph) * 100.0
    return 0.0


def normalize_turbidity(turbidity: float) -> float:
    if not math.isfinite(turbidity) or turbidity < 0.0:
        raise ValueError("Turbidity must be finite and non-negative.")
    if turbidity <= 1.0:
        return 100.0
    if turbidity < 5.0:
        return ((5.0 - turbidity) / 4.0) * 100.0
    return 0.0


def normalize_ec(ec: float) -> float:
    if not math.isfinite(ec) or ec < 0.0:
        raise ValueError(
            "Electrical conductivity must be finite and non-negative."
        )
    if ec <= 1000.0:
        return 100.0
    if ec < 1500.0:
        return ((1500.0 - ec) / 500.0) * 100.0
    return 0.0


def assign_wqi_status(score: float) -> WqiStatus:
    if not math.isfinite(score) or not 0.0 <= score <= 100.0:
        raise ValueError("WQI score must be between 0 and 100.")
    if score > 79.0:
        return WqiStatus.EXCELLENT
    if score > 51.0:
        return WqiStatus.GOOD
    if score > 36.0:
        return WqiStatus.REGULAR
    if score > 19.0:
        return WqiStatus.POOR
    return WqiStatus.VERY_POOR


def fetch_active_weights(db: Session) -> dict[str, float]:
    records = db.query(WqiWeight).all()
    return {record.parameter: record.weight / 100.0 for record in records}


def ingest_sensor_reading(
    db: Session,
    payload: SensorReadingCreate,
) -> SensorReading:
    try:
        device_uuid = uuid.UUID(payload.device_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Device ID '{payload.device_id}' not found. "
                "Please register the device first."
            ),
        ) from None

    device = (
        db.query(Device)
        .filter(Device.device_id == device_uuid)
        .first()
    )

    if device is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Device ID '{payload.device_id}' not found. "
                "Please register the device first."
            ),
        )

    existing_reading = get_reading_by_device_and_message(
        db,
        device_uuid,
        payload.message_number,
    )

    if existing_reading:
        return existing_reading

    wqi_score = None
    wqi_status = None

    if payload.sensor_status == SensorStatus.OK:
        weights = fetch_active_weights(db)

        if len(weights) == len(PARAMETERS) and PARAMETERS.issubset(weights):
            try:
                scores = {
                    "ph": normalize_ph(payload.ph),
                    "temperature": normalize_temperature(
                        payload.temperature
                    ),
                    "turbidity": normalize_turbidity(
                        payload.turbidity
                    ),
                    "electrical_conductivity": normalize_ec(
                        payload.electrical_conductivity
                    ),
                }
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc

            wqi_score = round(
                sum(
                    scores[parameter] * weights[parameter]
                    for parameter in PARAMETERS
                ),
                2,
            )
            wqi_status = assign_wqi_status(wqi_score)

    now = datetime.now(timezone.utc)
    is_buffered = (
        now - payload.recorded_at
    ).total_seconds() > 300

    reading_data = {
        "device_id": device_uuid,
        "message_number": payload.message_number,
        "ph": payload.ph,
        "temperature": payload.temperature,
        "turbidity": payload.turbidity,
        "electrical_conductivity": payload.electrical_conductivity,
        "wqi_score": wqi_score,
        "wqi_status": wqi_status,
        "sensor_status": payload.sensor_status,
        "is_buffered": is_buffered,
        "recorded_at": payload.recorded_at,
    }

    try:
        new_reading = create_reading(db, reading_data)
        db.commit()
        db.refresh(new_reading)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail=(
                f"Device ID '{payload.device_id}' does not exist. "
                "Please register the device first."
            ),
        ) from exc

    alert_service.process_new_reading(db, new_reading.reading_id)

    return new_reading


def list_sensor_readings(
    db: Session,
    device_id: str | None = None,
    limit: int = 100,
) -> list[SensorReading]:
    if device_id:
        try:
            device_uuid = uuid.UUID(device_id)
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=404,
                detail=f"Device ID '{device_id}' not found.",
            ) from None
    else:
        device_uuid = None

    return get_readings(
        db=db,
        device_id=device_uuid,
        limit=limit,
    )


def find_sensor_reading(
    db: Session,
    reading_id: str,
) -> SensorReading:
    try:
        reading_uuid = uuid.UUID(reading_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Sensor reading with ID '{reading_id}' not found."
            ),
        ) from None

    reading = get_reading_by_id(
        db=db,
        reading_id=reading_uuid,
    )

    if reading is None:
        raise HTTPException(
            status_code=404,
            detail="Sensor reading not found.",
        )

    return reading


def list_latest_readings_per_device(
    db: Session,
) -> list[SensorReading]:
    return get_latest_reading_per_device(db=db)


def list_readings_by_device(
    db: Session,
    device_id: str,
    limit: int = 100,
) -> list[SensorReading]:
    try:
        device_uuid = uuid.UUID(device_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=404,
            detail=f"Device ID '{device_id}' not found.",
        ) from None

    return get_readings_by_device(
        db=db,
        device_id=device_uuid,
        limit=limit,
    )

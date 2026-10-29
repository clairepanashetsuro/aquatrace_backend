from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from database import get_db
from schemas.sensor_reading import SensorReadingCreate, SensorReadingResponse
from services.sensor_reading_service import (
    list_sensor_readings,
    find_sensor_reading,
    list_latest_readings_per_device,
    list_readings_by_device,
    ingest_sensor_reading,
)

router = APIRouter(
    prefix="/sensor-readings",
    tags=["Sensor Readings"],
)


@router.post(
    "/", response_model=SensorReadingResponse, status_code=status.HTTP_201_CREATED
)
def create_sensor_reading(
    payload: SensorReadingCreate,
    db: Session = Depends(get_db),
):
    return ingest_sensor_reading(db=db, payload=payload)


@router.get("/", response_model=list[SensorReadingResponse])
def read_sensor_readings(
    device_id: str | None = Query(default=None),  # <--- Changed to str
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_sensor_readings(
        db=db,
        device_id=device_id,
        limit=limit,
    )


@router.get("/latest", response_model=list[SensorReadingResponse])
def read_latest_sensor_readings(
    db: Session = Depends(get_db),
):
    return list_latest_readings_per_device(db=db)


@router.get("/device/{device_id}", response_model=list[SensorReadingResponse])
def read_sensor_readings_by_device(
    device_id: str,  # <--- Changed to str
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_readings_by_device(
        db=db,
        device_id=device_id,
        limit=limit,
    )


@router.get("/{reading_id}", response_model=SensorReadingResponse)
def read_sensor_reading(
    reading_id: str,  # <--- Changed to str
    db: Session = Depends(get_db),
):
    return find_sensor_reading(
        db=db,
        reading_id=reading_id,
    )

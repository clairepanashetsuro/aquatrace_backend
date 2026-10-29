from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from core.gps_auth import require_gps_integration
from database import get_db
from dependencies import (
    get_current_user,
    require_water_quality_officer,
)
from models.user import User
from schemas.device import (
    DeviceCreate,
    DeviceGPSUpdate,
    DeviceResponse,
    DeviceUpdate,
)
from services.device import DeviceService


router = APIRouter(tags=["Devices"])


@router.post(
    "/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_device_route(
    data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_water_quality_officer),
):
    return DeviceService(db).create_device(data, current_user)


@router.get(
    "/devices",
    response_model=List[DeviceResponse],
)
def list_devices_route(
    device_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DeviceService(db).list_devices(status=device_status)


@router.patch(
    "/devices/gps",
    response_model=DeviceResponse,
    status_code=status.HTTP_200_OK,
)
def update_device_gps_route(
    data: DeviceGPSUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_gps_integration),
):
    return DeviceService(db).update_device_gps(data)


@router.get(
    "/devices/{device_id}",
    response_model=DeviceResponse,
)
def get_device_route(
    device_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DeviceService(db).get_device(device_id)


@router.patch(
    "/devices/{device_id}",
    response_model=DeviceResponse,
)
def update_device_route(
    data: DeviceUpdate,
    device_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DeviceService(db).update_device(device_id, data)


@router.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_device_route(
    device_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    DeviceService(db).delete_device(device_id)
    return None

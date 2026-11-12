import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.maintenance_record import MaintenanceStatus, MaintenanceType
from schemas.maintenance_record import (
    MaintenanceRecordCreate,
    MaintenanceRecordPage,
    MaintenanceRecordRead,
    MaintenanceRecordUpdate,
)
from services.maintenance_record import (
    MaintenanceRecordService,
    ensure_can_read,
    ensure_can_write,
)

router = APIRouter(prefix="/maintenance-records", tags=["Maintenance Records"])


def require_read_role(current_user=Depends(get_current_user)):
    ensure_can_read(current_user)
    return current_user


def require_write_role(current_user=Depends(get_current_user)):
    ensure_can_write(current_user)
    return current_user


@router.post(
    "",
    response_model=MaintenanceRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_record(
    payload: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return MaintenanceRecordService(db).create(payload, current_user)


@router.get(
    "",
    response_model=MaintenanceRecordPage,
    dependencies=[Depends(get_current_user)],
)
def list_maintenance_records(
    device_id: uuid.UUID | None = None,
    incident_id: uuid.UUID | None = None,
    performed_by: uuid.UUID | None = None,
    maintenance_type: MaintenanceType | None = None,
    status: MaintenanceStatus | None = None,
    performed_from: datetime | None = None,
    performed_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(require_read_role),
    db: Session = Depends(get_db),
):
    items, total = MaintenanceRecordService(db).list(
        current_user,
        device_id=device_id,
        incident_id=incident_id,
        performed_by=performed_by,
        maintenance_type=maintenance_type,
        status=status,
        performed_from=performed_from,
        performed_to=performed_to,
        limit=limit,
        offset=offset,
    )
    return MaintenanceRecordPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{maintenance_id}",
    response_model=MaintenanceRecordRead,
    dependencies=[Depends(get_current_user)],
)
def get_maintenance_record(
    maintenance_id: uuid.UUID,
    current_user=Depends(require_read_role),
    db: Session = Depends(get_db),
):
    return MaintenanceRecordService(db).get(maintenance_id, current_user)


@router.patch(
    "/{maintenance_id}",
    response_model=MaintenanceRecordRead,
)
def update_maintenance_record(
    maintenance_id: uuid.UUID,
    payload: MaintenanceRecordUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return MaintenanceRecordService(db).update(
        maintenance_id,
        payload,
        current_user,
    )

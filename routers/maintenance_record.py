import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from database import get_db
from models.maintenance_record import MaintenanceStatus, MaintenanceType
from schemas.maintenance_record import (
    MaintenanceRecordCreate,
    MaintenanceRecordPage,
    MaintenanceRecordRead,
    MaintenanceRecordUpdate,
)
from services.maintenance_record import MaintenanceRecordService, ensure_can_write

router = APIRouter(prefix="/maintenance-records", tags=["Maintenance Records"])


def get_current_user(
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    return MaintenanceRecordService(db).resolve_active_user(x_user_id)


def require_write_role(current_user=Depends(get_current_user)):
    ensure_can_write(current_user)
    return current_user


@router.post(
    "", response_model=MaintenanceRecordRead, status_code=status.HTTP_201_CREATED
)
def create_maintenance_record(
    payload: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return MaintenanceRecordService(db).create(payload, current_user)


@router.get(
    "", response_model=MaintenanceRecordPage, dependencies=[Depends(get_current_user)]
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
    db: Session = Depends(get_db),
):
    items, total = MaintenanceRecordService(db).list(
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
    return MaintenanceRecordPage(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{maintenance_id}",
    response_model=MaintenanceRecordRead,
    dependencies=[Depends(get_current_user)],
)
def get_maintenance_record(maintenance_id: uuid.UUID, db: Session = Depends(get_db)):
    return MaintenanceRecordService(db).get(maintenance_id)


@router.patch("/{maintenance_id}", response_model=MaintenanceRecordRead)
def update_maintenance_record(
    maintenance_id: uuid.UUID,
    payload: MaintenanceRecordUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return MaintenanceRecordService(db).update(maintenance_id, payload, current_user)

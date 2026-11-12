import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from schemas.lab_test import (
    LabTestCreate,
    LabTestPage,
    LabTestRead,
    LabTestUpdate,
)
from services.lab_test import (
    LabTestService,
    ensure_can_read,
    ensure_can_write,
)

router = APIRouter(prefix="/lab-tests", tags=["Lab Tests"])


def require_read_role(current_user=Depends(get_current_user)):
    ensure_can_read(current_user)
    return current_user


def require_write_role(current_user=Depends(get_current_user)):
    ensure_can_write(current_user)
    return current_user


@router.post("", response_model=LabTestRead, status_code=status.HTTP_201_CREATED)
def create_lab_test(
    payload: LabTestCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return LabTestService(db).create(payload, current_user)


@router.get("", response_model=LabTestPage)
def list_lab_tests(
    incident_id: uuid.UUID | None = None,
    recorded_by: uuid.UUID | None = None,
    parameter: str | None = Query(default=None, max_length=50),
    laboratory_name: str | None = Query(default=None, max_length=100),
    sampled_from: datetime | None = None,
    sampled_to: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user=Depends(require_read_role),
    db: Session = Depends(get_db),
):
    items, total = LabTestService(db).list(
        current_user,
        incident_id=incident_id,
        recorded_by=recorded_by,
        parameter=parameter,
        laboratory_name=laboratory_name,
        sampled_from=sampled_from,
        sampled_to=sampled_to,
        limit=limit,
        offset=offset,
    )
    return LabTestPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{lab_test_id}", response_model=LabTestRead)
def get_lab_test(
    lab_test_id: uuid.UUID,
    current_user=Depends(require_read_role),
    db: Session = Depends(get_db),
):
    return LabTestService(db).get(lab_test_id, current_user)


@router.patch("/{lab_test_id}", response_model=LabTestRead)
def update_lab_test(
    lab_test_id: uuid.UUID,
    payload: LabTestUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_write_role),
):
    return LabTestService(db).update(lab_test_id, payload, current_user)

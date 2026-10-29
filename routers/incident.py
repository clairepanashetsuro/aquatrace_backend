from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from database import get_db
from models.incident import IncidentPriority, IncidentStatus
from repositories.incident import IncidentRepository
from schemas.incident import (
    IncidentAssign,
    IncidentCreate,
    IncidentPage,
    IncidentRead,
    IncidentUpdate,
)
from services.incident import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])


def get_service(db: Session = Depends(get_db)) -> IncidentService:
    return IncidentService(IncidentRepository(db))


def get_current_user(
    x_user_id: Optional[UUID] = Header(default=None, alias="X-User-Id"),
    service: IncidentService = Depends(get_service),
):
    return service.resolve_active_user(x_user_id)


@router.post("", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
def create_incident(
    body: IncidentCreate,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.create(caller, body.model_dump())


@router.get("", response_model=IncidentPage)
def list_incidents(
    status_: Optional[IncidentStatus] = Query(default=None, alias="status"),
    priority: Optional[IncidentPriority] = None,
    assigned_to: Optional[UUID] = None,
    alert_id: Optional[UUID] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    limit: int = 20,
    offset: int = 0,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    items, total = service.list(
        caller,
        limit,
        offset,
        status_,
        priority,
        assigned_to,
        alert_id,
        created_from,
        created_to,
    )
    return IncidentPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(
    incident_id: UUID,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.get(caller, incident_id)


@router.patch("/{incident_id}", response_model=IncidentRead)
def update_incident(
    incident_id: UUID,
    body: IncidentUpdate,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    changes = body.model_dump(exclude_unset=True)
    return service.update(caller, incident_id, changes)


@router.patch("/{incident_id}/assign", response_model=IncidentRead)
def assign_incident(
    incident_id: UUID,
    body: IncidentAssign,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.assign(caller, incident_id, body.assigned_to)


@router.post("/{incident_id}/submit", response_model=IncidentRead)
def submit_incident(
    incident_id: UUID,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.submit(caller, incident_id)


@router.post("/{incident_id}/reopen", response_model=IncidentRead)
def reopen_incident(
    incident_id: UUID,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.reopen(caller, incident_id)


@router.post("/{incident_id}/close", response_model=IncidentRead)
def close_incident(
    incident_id: UUID,
    caller=Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return service.close(caller, incident_id)

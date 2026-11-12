from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.alert import AlertStatus, AlertType, SeverityLevel
from models.incident import IncidentPriority, IncidentStatus


class IncidentDeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: UUID
    serial_number: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None


class IncidentAlertSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: UUID
    device_id: UUID
    reading_id: Optional[UUID] = None
    alert_type: AlertType
    parameter: Optional[str] = None
    observed_value: Optional[float] = None
    threshold_value: Optional[float] = None
    severity: SeverityLevel
    message: str
    status: AlertStatus
    created_at: datetime
    device: IncidentDeviceSummary


class IncidentCreate(BaseModel):
    alert_id: UUID
    priority: IncidentPriority
    assigned_to: Optional[UUID] = None


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: Optional[str] = None
    corrective_action: Optional[str] = None
    visited_at: Optional[datetime] = None
    priority: Optional[IncidentPriority] = None


class IncidentAssign(BaseModel):
    assigned_to: UUID


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    first_name: str
    last_name: str


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incident_id: UUID
    alert_id: UUID
    assigned_to: Optional[UUID] = None
    resolved_by: Optional[UUID] = None
    findings: Optional[str] = None
    corrective_action: Optional[str] = None
    visited_at: Optional[datetime] = None
    status: IncidentStatus
    priority: IncidentPriority
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    alert: Optional[IncidentAlertSummary] = None
    assignee: Optional[UserSummary] = Field(
        default=None, validation_alias="assigned_user"
    )
    resolver: Optional[UserSummary] = Field(
        default=None, validation_alias="resolved_user"
    )


class IncidentPage(BaseModel):
    items: List[IncidentRead]
    total: int
    limit: int
    offset: int

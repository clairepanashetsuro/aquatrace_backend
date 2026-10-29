from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.alert import AlertStatus, AlertType, SeverityLevel


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: UUID
    device_id: UUID
    reading_id: UUID | None
    alert_type: AlertType
    parameter: str | None
    observed_value: float | None
    threshold_value: float | None
    severity: SeverityLevel
    message: str
    status: AlertStatus
    occurrence_count: int
    device_serial_number: str
    location_name: str
    ai_explanation: str | None
    ai_generated_at: datetime | None
    officers_notified_at: datetime | None
    created_at: datetime
    seen_at: datetime | None


class AlertSeenUpdate(BaseModel):
    seen: bool = Field(description="Whether the alert has been seen")


class AlertResolveUpdate(BaseModel):
    status: AlertStatus

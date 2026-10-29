import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.maintenance_record import MaintenanceStatus, MaintenanceType
from models.user import UserRole


class MaintenanceRecordBase(BaseModel):
    incident_id: uuid.UUID | None = None
    maintenance_type: MaintenanceType
    performed_at: datetime
    notes: str | None = Field(default=None, max_length=5000)
    status: MaintenanceStatus = MaintenanceStatus.COMPLETED
    pre_maintenance_value: float | None = None
    post_maintenance_value: float | None = None
    next_scheduled_date: datetime | None = None


class MaintenanceRecordCreate(MaintenanceRecordBase):
    device_id: uuid.UUID


class MaintenanceRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: uuid.UUID | None = None
    maintenance_type: MaintenanceType | None = None
    performed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)
    status: MaintenanceStatus | None = None
    pre_maintenance_value: float | None = None
    post_maintenance_value: float | None = None
    next_scheduled_date: datetime | None = None


class PerformerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    first_name: str
    last_name: str
    role: UserRole


class DeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: uuid.UUID
    serial_number: str
    latitude: float
    longitude: float
    address: str | None = None
    name: str | None = None


class MaintenanceRecordRead(MaintenanceRecordBase):
    model_config = ConfigDict(from_attributes=True)

    maintenance_id: uuid.UUID
    device_id: uuid.UUID
    performed_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    performer: PerformerSummary | None = Field(default=None, validation_alias="user")
    device: DeviceSummary | None = None


class MaintenanceRecordPage(BaseModel):
    items: list[MaintenanceRecordRead]
    total: int
    limit: int
    offset: int

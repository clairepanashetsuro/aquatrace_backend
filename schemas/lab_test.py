import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.user import UserRole


class LabTestBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    laboratory_name: str = Field(min_length=1, max_length=100)
    parameter: str = Field(min_length=1, max_length=50)
    result_value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=20)
    sample_collected_at: datetime
    tested_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)


class LabTestCreate(LabTestBase):
    incident_id: uuid.UUID


class LabTestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    laboratory_name: str | None = Field(default=None, min_length=1, max_length=100)
    parameter: str | None = Field(default=None, min_length=1, max_length=50)
    result_value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    sample_collected_at: datetime | None = None
    tested_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)


class RecorderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    first_name: str
    last_name: str
    role: UserRole


class LabTestRead(LabTestBase):
    model_config = ConfigDict(from_attributes=True)

    lab_test_id: uuid.UUID
    incident_id: uuid.UUID
    recorded_by: uuid.UUID

    recorder: RecorderSummary | None = Field(default=None, validation_alias="user")
    created_at: datetime


class LabTestPage(BaseModel):
    items: list[LabTestRead]
    total: int
    limit: int
    offset: int

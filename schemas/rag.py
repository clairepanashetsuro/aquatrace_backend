
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RAGSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class RAGExplanation(RAGSchema):
    what_changed: str = Field(min_length=1, max_length=1200)
    evidence_used: list[str] = Field(max_length=8)
    still_to_confirm: list[str] = Field(max_length=6)
    ideas_to_check: list[str] = Field(max_length=6)
    missing_information: list[str] = Field(max_length=8)


class RAGSensorReadingContext(RAGSchema):
    reading_id: UUID
    ph: float
    temperature: float
    turbidity: float
    electrical_conductivity: float
    wqi_score: float | None
    wqi_status: str | None
    sensor_status: str
    recorded_at: datetime


class RAGDeviceContext(RAGSchema):
    device_id: UUID
    serial_number: str
    location_name: str | None


class RAGAlertContext(RAGSchema):
    alert_id: UUID
    device_id: UUID
    reading_id: UUID | None
    alert_type: str
    parameter: str | None
    observed_value: float | None
    threshold_value: float | None
    severity: str
    status: str
    message: str
    occurrence_count: int
    created_at: datetime


class RAGContext(RAGSchema):
    alert: RAGAlertContext
    device: RAGDeviceContext
    reading: RAGSensorReadingContext | None
    missing_information: list[str] = Field(max_length=8)


class RAGSourceCitation(RAGSchema):
    source_file: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    review_status: str | None = Field(default=None, max_length=50)
    source_sha256: str | None = Field(default=None, max_length=64)
    start_index: int | None = Field(default=None, ge=0)
    end_index: int | None = Field(default=None, ge=0)


class RAGAlertExplanation(RAGExplanation):
    alert_id: UUID
    model: str = Field(min_length=1, max_length=100)
    sources: list[RAGSourceCitation] = Field(default_factory=list, max_length=8)

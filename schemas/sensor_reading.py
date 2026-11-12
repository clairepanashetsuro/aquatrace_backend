from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator
from uuid import UUID
from models.sensor_reading import WqiStatus, SensorStatus


class SensorReadingCreate(BaseModel):
    device_id: str | None = Field(
        default=None, description="The UUID of the registered device"
    )
    serial_number: str | None = Field(default=None, min_length=1, max_length=50)

    message_number: int = Field(..., ge=1)
    ph: float = Field(..., ge=0, le=14)
    temperature: float
    turbidity: float = Field(..., ge=0)
    electrical_conductivity: float = Field(..., ge=0)

    recorded_at: datetime
    sensor_status: SensorStatus = SensorStatus.OK

    @model_validator(mode="after")
    def require_exactly_one_identifier(self):
        if (self.device_id is None) == (self.serial_number is None):
            raise ValueError("Provide exactly one of device_id or serial_number.")
        return self


class SensorReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reading_id: UUID
    device_id: UUID
    message_number: int
    ph: float
    temperature: float
    turbidity: float
    electrical_conductivity: float
    wqi_score: float | None = None
    wqi_status: WqiStatus | None = None
    sensor_status: SensorStatus
    is_buffered: bool
    recorded_at: datetime
    created_at: datetime

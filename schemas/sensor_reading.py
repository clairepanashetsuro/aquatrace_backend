from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from models.sensor_reading import WqiStatus, SensorStatus


class SensorReadingCreate(BaseModel):
    device_id: str = Field(..., description="The UUID of the registered device")
    message_number: int = Field(..., ge=1)
    ph: float = Field(..., ge=0, le=14)
    temperature: float
    turbidity: float = Field(..., ge=0)
    electrical_conductivity: float = Field(..., ge=0)

    recorded_at: datetime
    sensor_status: SensorStatus = SensorStatus.OK


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

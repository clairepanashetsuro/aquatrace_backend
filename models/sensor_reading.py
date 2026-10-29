
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class WqiStatus(str, PyEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    REGULAR = "regular"
    POOR = "poor"
    VERY_POOR = "very_poor"


class SensorStatus(str, PyEnum):
    OK = "ok"
    FAULT = "fault"


def get_enum_values(enum_class):
    return [member.value for member in enum_class]


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "message_number", name="uq_reading_device_message"
        ),
        CheckConstraint("ph BETWEEN 0 AND 14", name="ck_sensor_readings_ph"),
    )

    reading_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    message_number = Column(Integer, nullable=False)
    ph = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    turbidity = Column(Float, nullable=False)
    electrical_conductivity = Column(Float, nullable=False)
    wqi_score = Column(Float, nullable=True)

    wqi_status = Column(
        Enum(
            WqiStatus,
            name="wqi_status",
            values_callable=get_enum_values,
        ),
        nullable=True,
    )
    sensor_status = Column(
        Enum(
            SensorStatus,
            name="sensor_status",
            values_callable=get_enum_values,
        ),
        nullable=False,
        default=SensorStatus.OK,
    )
    is_buffered = Column(Boolean, nullable=False, default=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    device = relationship("Device", back_populates="sensor_readings")
    alerts = relationship("Alert", back_populates="reading")

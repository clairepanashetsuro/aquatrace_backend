
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class AlertType(str, PyEnum):
    THRESHOLD_BREACH = "threshold_breach"
    WQI_CHANGE = "wqi_change"
    DEVICE_OFFLINE = "device_offline"
    TAMPER = "tamper"
    SENSOR_FAULT = "sensor_fault"


class SeverityLevel(str, PyEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, PyEnum):
    TRIGGERED = "triggered"
    RESOLVED = "resolved"


def get_enum_values(enum_class):
    return [member.value for member in enum_class]


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "parameter IN "
            "('ph', 'temperature', 'turbidity', 'electrical_conductivity')",
            name="ck_alerts_parameter",
        ),
    )

    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reading_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_readings.reading_id", ondelete="RESTRICT"),
        nullable=True,
    )

    alert_type = Column(
        Enum(
            AlertType,
            name="alert_type",
            values_callable=get_enum_values,
        ),
        nullable=False,
    )
    parameter = Column(String(30), nullable=True)
    observed_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)

    severity = Column(
        Enum(
            SeverityLevel,
            name="severity_level",
            values_callable=get_enum_values,
        ),
        nullable=False,
    )
    message = Column(Text, nullable=False)

    status = Column(
        Enum(
            AlertStatus,
            name="alert_status",
            values_callable=get_enum_values,
        ),
        nullable=False,
        default=AlertStatus.TRIGGERED,
    )
    occurrence_count = Column(Integer, nullable=False, default=1, server_default="1")
    ai_explanation = Column(Text, nullable=True)
    ai_generated_at = Column(DateTime(timezone=True), nullable=True)
    seen_at = Column(DateTime(timezone=True), nullable=True)
    officers_notified_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    device = relationship("Device", back_populates="alerts")
    reading = relationship("SensorReading", back_populates="alerts")
    incident = relationship("Incident", back_populates="alert", uselist=False)

    @property
    def device_serial_number(self) -> str:
        return self.device.serial_number

    @property
    def location_name(self) -> str | None:
        return self.device.address

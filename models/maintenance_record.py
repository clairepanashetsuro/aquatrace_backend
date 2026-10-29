from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class MaintenanceType(str, PyEnum):
    CALIBRATION = "calibration"
    CLEANING = "cleaning"
    REPAIR = "repair"


class MaintenanceStatus(str, PyEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    maintenance_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(
        UUID(as_uuid=True),
        ForeignKey("devices.device_id", ondelete="RESTRICT"),
        nullable=False,
    )
    performed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    incident_id = Column(
        UUID(as_uuid=True),
        ForeignKey("incidents.incident_id", ondelete="SET NULL"),
        nullable=True,
    )
    maintenance_type = Column(
        Enum(
            MaintenanceType,
            name="maintenance_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    performed_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    status = Column(
        Enum(
            MaintenanceStatus,
            name="maintenance_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=MaintenanceStatus.COMPLETED.value,
    )
    pre_maintenance_value = Column(Float, nullable=True)
    post_maintenance_value = Column(Float, nullable=True)
    next_scheduled_date = Column(DateTime(timezone=True), nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    device = relationship("Device", back_populates="maintenance_records")
    user = relationship("User", back_populates="maintenance_records")
    incident = relationship("Incident", back_populates="maintenance_records")

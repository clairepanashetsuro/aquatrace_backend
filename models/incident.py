from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class IncidentStatus(str, PyEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_VERIFICATION = "awaiting_verification"
    CLOSED = "closed"


class IncidentPriority(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Incident(Base):
    __tablename__ = "incidents"

    incident_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    alert_id = Column(
        UUID(as_uuid=True),
        ForeignKey("alerts.alert_id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    findings = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    visited_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        Enum(IncidentStatus, name="incident_status"),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    priority = Column(
        Enum(IncidentPriority, name="incident_priority"),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)

    alert = relationship("Alert", back_populates="incident")
    assigned_user = relationship(
        "User", foreign_keys=[assigned_to], back_populates="assigned_incidents"
    )
    resolved_user = relationship(
        "User", foreign_keys=[resolved_by], back_populates="resolved_incidents"
    )
    maintenance_records = relationship("MaintenanceRecord", back_populates="incident")
    lab_tests = relationship("LabTest", back_populates="incident")

from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class DeviceStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class Device(Base):
    __tablename__ = "devices"

    __table_args__ = (
        CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_devices_revoked_at",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_devices_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_devices_longitude",
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="ck_devices_coordinates_together",
        ),
    )

    device_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    serial_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(
            DeviceStatus,
            name="device_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DeviceStatus.ACTIVE,
    )

    description = Column(Text, nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address = Column(String(255), nullable=True)

    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    installed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="devices")
    sensor_readings = relationship(
        "SensorReading",
        back_populates="device",
    )
    alerts = relationship("Alert", back_populates="device")
    maintenance_records = relationship(
        "MaintenanceRecord",
        back_populates="device",
    )

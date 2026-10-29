from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from database import Base


class UserRole(str, PyEnum):
    WATER_QUALITY_OFFICER = "Water quality officer"
    FIELD_OFFICER = "Field officer"
    ADMIN = "Admin"


class UserStatus(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("otp_attempts >= 0", name="ck_users_otp_attempts"),
        CheckConstraint(
            "failed_login_attempts >= 0", name="ck_users_failed_login_attempts"
        ),
        CheckConstraint(
            "mfa_enabled = false OR totp_secret IS NOT NULL",
            name="ck_users_totp_secret_when_mfa",
        ),
    )

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)

    role = Column(
        Enum(UserRole, name="user_role"),
        nullable=False,
    )
    status = Column(
        Enum(UserStatus, name="user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    totp_secret = Column(String(255), nullable=True)
    recovery_code_hashes = Column(ARRAY(Text), nullable=True)
    otp_hash = Column(String(255), nullable=True)
    otp_expires_at = Column(DateTime(timezone=True), nullable=True)
    otp_attempts = Column(Integer, nullable=False, default=0)
    mfa_challenge_hash = Column(String(64), nullable=True)
    mfa_challenge_expires_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    assigned_incidents = relationship(
        "Incident",
        foreign_keys="Incident.assigned_to",
        back_populates="assigned_user",
    )
    resolved_incidents = relationship(
        "Incident",
        foreign_keys="Incident.resolved_by",
        back_populates="resolved_user",
    )
    audit_logs = relationship("AuditLog", back_populates="user")
    maintenance_records = relationship("MaintenanceRecord", back_populates="user")
    lab_tests = relationship("LabTest", back_populates="user")
    devices = relationship("Device", back_populates="user")

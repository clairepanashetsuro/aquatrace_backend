from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class LabTest(Base):
    __tablename__ = "lab_tests"
    __table_args__ = (
        CheckConstraint(
            "tested_at >= sample_collected_at", name="ck_lab_tests_tested_after_sample"
        ),
    )

    lab_test_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id = Column(
        UUID(as_uuid=True),
        ForeignKey("incidents.incident_id", ondelete="RESTRICT"),
        nullable=False,
    )
    recorded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    laboratory_name = Column(String(100), nullable=False)
    parameter = Column(String(50), nullable=False)
    result_value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    sample_collected_at = Column(DateTime(timezone=True), nullable=False)
    tested_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    incident = relationship("Incident", back_populates="lab_tests")
    user = relationship("User", back_populates="lab_tests")

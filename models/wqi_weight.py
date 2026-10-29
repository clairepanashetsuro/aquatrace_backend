from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, Float, String
from sqlalchemy.dialects.postgresql import UUID

from database import Base


class WqiWeight(Base):
    __tablename__ = "wqi_weights"
    __table_args__ = (
        CheckConstraint(
            "parameter IN ('ph', 'temperature', 'turbidity', 'electrical_conductivity')",
            name="ck_wqi_weights_parameter",
        ),
        CheckConstraint("weight > 0 AND weight <= 100", name="ck_wqi_weights_weight"),
    )

    wqi_weight_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    parameter = Column(String(30), nullable=False)
    weight = Column(Float, nullable=False)

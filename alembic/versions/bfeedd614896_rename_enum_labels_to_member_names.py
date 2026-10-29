"""rename enum labels to member names

Revision ID: bfeedd614896
Revises: 3ee6a2e96c84
Create Date: 2026-10-20 23:21:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bfeedd614896"
down_revision: Union[str, None] = "3ee6a2e96c84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RENAMES = {
    "gemini_file_status": {"active": "ACTIVE", "expired": "EXPIRED"},
    "user_role": {
        "Water quality officer": "WATER_QUALITY_OFFICER",
        "Field officer": "FIELD_OFFICER",
        "Admin": "ADMIN",
    },
    "user_status": {"active": "ACTIVE", "inactive": "INACTIVE"},
    "wqi_status": {"good": "GOOD", "poor": "POOR"},
    "sensor_status": {"ok": "OK", "fault": "FAULT"},
    "alert_type": {
        "threshold_breach": "THRESHOLD_BREACH",
        "wqi_change": "WQI_CHANGE",
        "device_offline": "DEVICE_OFFLINE",
        "tamper": "TAMPER",
        "sensor_fault": "SENSOR_FAULT",
    },
    "severity_level": {"warning": "WARNING", "critical": "CRITICAL"},
    "alert_status": {"triggered": "TRIGGERED", "resolved": "RESOLVED"},
    "incident_status": {
        "open": "OPEN",
        "investigating": "INVESTIGATING",
        "awaiting_verification": "AWAITING_VERIFICATION",
        "closed": "CLOSED",
    },
    "incident_priority": {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"},
}


def upgrade() -> None:
    for type_name, labels in RENAMES.items():
        for old, new in labels.items():
            bind = op.get_bind()
    labels = {
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = :type_name
                """
            ),
            {"type_name": type_name},
        )
    }

    if old in labels and new not in labels:
        op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{old}' TO '{new}'")


def downgrade() -> None:
    for type_name, labels in RENAMES.items():
        for old, new in labels.items():
            op.execute(f"ALTER TYPE {type_name} RENAME VALUE '{new}' TO '{old}'")

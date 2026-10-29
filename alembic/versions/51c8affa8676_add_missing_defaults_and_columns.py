"""add_missing_defaults_and_columns

Revision ID: 51c8affa8676
Revises: e138f5c6da84
Create Date: 2026-10-14 14:06:40.580664

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "51c8affa8676"
down_revision: Union[str, Sequence[str], None] = "e138f5c6da84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users table: add defaults
    op.alter_column("users", "mfa_enabled", server_default=sa.false())
    op.alter_column("users", "otp_attempts", server_default=sa.text("0"))
    op.alter_column("users", "failed_login_attempts", server_default=sa.text("0"))
    # Note: onupdate is not a database-level feature, it's handled by SQLAlchemy ORM

    # devices table: add default for status
    op.alter_column(
        "devices",
        "status",
        server_default=sa.text("'active'::device_status"),
        existing_type=sa.Enum("active", "inactive", "revoked", name="device_status"),
    )

    # sensor_readings table: add defaults
    op.alter_column(
        "sensor_readings",
        "sensor_status",
        server_default=sa.text("'ok'::sensor_status"),
        existing_type=sa.Enum("ok", "fault", name="sensor_status"),
    )
    op.alter_column("sensor_readings", "is_buffered", server_default=sa.false())

    # alerts table: add default for status
    op.alter_column(
        "alerts",
        "status",
        server_default=sa.text("'triggered'::alert_status"),
        existing_type=sa.Enum("triggered", "resolved", name="alert_status"),
    )

    # incidents table: add default for status
    op.alter_column(
        "incidents",
        "status",
        server_default=sa.text("'open'::incident_status"),
        existing_type=sa.Enum(
            "open",
            "investigating",
            "awaiting_verification",
            "closed",
            name="incident_status",
        ),
    )
    # Note: onupdate is not a database-level feature, it's handled by SQLAlchemy ORM

    # gemini_files table: add defaults
    op.alter_column(
        "gemini_files", "mime_type", server_default=sa.text("'text/markdown'")
    )
    op.alter_column(
        "gemini_files",
        "status",
        server_default=sa.text("'active'::gemini_file_status"),
        existing_type=sa.Enum("active", "expired", name="gemini_file_status"),
    )


def downgrade() -> None:
    # Remove defaults (set to NULL)
    op.alter_column("gemini_files", "status", server_default=None)
    op.alter_column("gemini_files", "mime_type", server_default=None)
    op.alter_column("incidents", "status", server_default=None)
    op.alter_column("alerts", "status", server_default=None)
    op.alter_column("sensor_readings", "is_buffered", server_default=None)
    op.alter_column("sensor_readings", "sensor_status", server_default=None)
    op.alter_column("devices", "status", server_default=None)
    op.alter_column("users", "failed_login_attempts", server_default=None)
    op.alter_column("users", "otp_attempts", server_default=None)
    op.alter_column("users", "mfa_enabled", server_default=None)

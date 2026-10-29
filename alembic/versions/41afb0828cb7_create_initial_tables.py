"""create initial tables

Revision ID: 41afb0828cb7
Revises:
Create Date: 2026-10-14 09:04:19.931996

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "41afb0828cb7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "gemini_files",
        sa.Column("gemini_file_id", sa.UUID(), nullable=False),
        sa.Column("source_document", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("gemini_file_name", sa.String(length=100), nullable=False),
        sa.Column("gemini_file_uri", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "expired", name="gemini_file_status"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > uploaded_at", name="ck_gemini_files_expires_after_upload"
        ),
        sa.PrimaryKeyConstraint("gemini_file_id"),
        sa.UniqueConstraint("gemini_file_name"),
    )
    op.create_index(
        "uq_gemini_files_active_document",
        "gemini_files",
        ["source_document"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "locations",
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("upstream_location_id", sa.UUID(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_locations_latitude"),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_locations_longitude"
        ),
        sa.CheckConstraint(
            "upstream_location_id <> location_id", name="ck_locations_not_own_upstream"
        ),
        sa.ForeignKeyConstraint(
            ["upstream_location_id"], ["locations.location_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("location_id"),
    )
    op.create_table(
        "users",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("first_name", sa.String(length=50), nullable=False),
        sa.Column("last_name", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "Water quality officer", "Field officer", "Admin", name="user_role"
            ),
            nullable=False,
        ),
        sa.Column(
            "status", sa.Enum("active", "inactive", name="user_status"), nullable=False
        ),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("recovery_code_hashes", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("otp_hash", sa.String(length=255), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_attempts", sa.Integer(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "failed_login_attempts >= 0", name="ck_users_failed_login_attempts"
        ),
        sa.CheckConstraint(
            "mfa_enabled = false OR totp_secret IS NOT NULL",
            name="ck_users_totp_secret_when_mfa",
        ),
        sa.CheckConstraint("otp_attempts >= 0", name="ck_users_otp_attempts"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "wqi_weights",
        sa.Column("wqi_weight_id", sa.UUID(), nullable=False),
        sa.Column("parameter", sa.String(length=30), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "parameter IN ('ph', 'temperature', 'turbidity', 'electrical_conductivity')",
            name="ck_wqi_weights_parameter",
        ),
        sa.CheckConstraint(
            "weight > 0 AND weight <= 100", name="ck_wqi_weights_weight"
        ),
        sa.PrimaryKeyConstraint("wqi_weight_id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("audit_log_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("audit_log_id"),
    )
    op.create_table(
        "devices",
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("serial_number", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "revoked", name="device_status"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name="ck_devices_revoked_at",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"], ["locations.location_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index(
        op.f("ix_devices_serial_number"), "devices", ["serial_number"], unique=True
    )
    op.create_table(
        "rejected_readings",
        sa.Column("rejected_reading_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column(
            "rejection_reason",
            sa.Enum(
                "out_of_range",
                "missing_value",
                "sensor_fault",
                "malformed_message",
                "duplicate_message",
                "revoked_device",
                "unknown_device",
                name="rejection_reason",
            ),
            nullable=False,
        ),
        sa.Column("rejection_detail", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("rejected_reading_id"),
    )
    op.create_table(
        "sensor_readings",
        sa.Column("reading_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("message_number", sa.Integer(), nullable=False),
        sa.Column("ph", sa.Float(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("turbidity", sa.Float(), nullable=False),
        sa.Column("electrical_conductivity", sa.Float(), nullable=False),
        sa.Column("wqi_score", sa.Float(), nullable=False),
        sa.Column(
            "wqi_status",
            sa.Enum("good", "moderate", "poor", name="wqi_status"),
            nullable=False,
        ),
        sa.Column(
            "sensor_status",
            sa.Enum("ok", "fault", name="sensor_status"),
            nullable=False,
        ),
        sa.Column("is_buffered", sa.Boolean(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("ph BETWEEN 0 AND 14", name="ck_sensor_readings_ph"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("reading_id"),
        sa.UniqueConstraint(
            "device_id", "message_number", name="uq_reading_device_message"
        ),
    )
    op.create_index(
        op.f("ix_sensor_readings_device_id"),
        "sensor_readings",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sensor_readings_recorded_at"),
        "sensor_readings",
        ["recorded_at"],
        unique=False,
    )
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("reading_id", sa.UUID(), nullable=True),
        sa.Column(
            "alert_type",
            sa.Enum(
                "threshold_breach",
                "wqi_change",
                "device_offline",
                "tamper",
                "sensor_fault",
                name="alert_type",
            ),
            nullable=False,
        ),
        sa.Column("parameter", sa.String(length=30), nullable=True),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("warning", "critical", name="severity_level"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("triggered", "resolved", name="alert_status"),
            nullable=False,
        ),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parameter IN ('ph', 'temperature', 'turbidity', 'electrical_conductivity')",
            name="ck_alerts_parameter",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reading_id"], ["sensor_readings.reading_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index(op.f("ix_alerts_device_id"), "alerts", ["device_id"], unique=False)
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("assigned_to", sa.UUID(), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "investigating",
                "awaiting_verification",
                "closed",
                name="incident_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", name="incident_priority"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.alert_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("incident_id"),
        sa.UniqueConstraint("alert_id"),
    )
    op.create_table(
        "lab_tests",
        sa.Column("lab_test_id", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=False),
        sa.Column("recorded_by", sa.UUID(), nullable=False),
        sa.Column("laboratory_name", sa.String(length=100), nullable=False),
        sa.Column("parameter", sa.String(length=50), nullable=False),
        sa.Column("result_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("sample_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tested_at >= sample_collected_at", name="ck_lab_tests_tested_after_sample"
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.incident_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("lab_test_id"),
    )
    op.create_table(
        "maintenance_records",
        sa.Column("maintenance_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("performed_by", sa.UUID(), nullable=False),
        sa.Column("incident_id", sa.UUID(), nullable=True),
        sa.Column(
            "maintenance_type",
            sa.Enum("calibration", "cleaning", "repair", name="maintenance_type"),
            nullable=False,
        ),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.device_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incidents.incident_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("maintenance_id"),
    )


def downgrade() -> None:
    op.drop_table("maintenance_records")
    op.drop_table("lab_tests")
    op.drop_table("incidents")
    op.drop_index(op.f("ix_alerts_device_id"), table_name="alerts")
    op.drop_table("alerts")
    op.drop_index(op.f("ix_sensor_readings_recorded_at"), table_name="sensor_readings")
    op.drop_index(op.f("ix_sensor_readings_device_id"), table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_table("rejected_readings")
    op.drop_index(op.f("ix_devices_serial_number"), table_name="devices")
    op.drop_table("devices")
    op.drop_table("audit_logs")
    op.drop_table("wqi_weights")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("locations")
    op.drop_index(
        "uq_gemini_files_active_document",
        table_name="gemini_files",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_table("gemini_files")

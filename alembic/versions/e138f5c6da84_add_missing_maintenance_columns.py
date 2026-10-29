"""Add missing maintenance columns

Revision ID: e138f5c6da84
Revises: 41afb0828cb7
Create Date: 2026-10-14 13:34:47.117027

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e138f5c6da84"
down_revision: Union[str, Sequence[str], None] = "41afb0828cb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    maintenance_status_enum = postgresql.ENUM(
        "scheduled",
        "in_progress",
        "completed",
        "failed",
        name="maintenance_status",
        create_type=True,
    )
    maintenance_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "maintenance_records",
        sa.Column(
            "status",
            maintenance_status_enum,
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "maintenance_records",
        sa.Column("pre_maintenance_value", sa.Float(), nullable=True),
    )
    op.add_column(
        "maintenance_records",
        sa.Column("post_maintenance_value", sa.Float(), nullable=True),
    )
    op.add_column(
        "maintenance_records",
        sa.Column("next_scheduled_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "maintenance_records",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("maintenance_records", "updated_at")
    op.drop_column("maintenance_records", "next_scheduled_date")
    op.drop_column("maintenance_records", "post_maintenance_value")
    op.drop_column("maintenance_records", "pre_maintenance_value")
    op.drop_column("maintenance_records", "status")
    maintenance_status_enum = postgresql.ENUM(
        "scheduled",
        "in_progress",
        "completed",
        "failed",
        name="maintenance_status",
    )
    maintenance_status_enum.drop(op.get_bind(), checkfirst=True)

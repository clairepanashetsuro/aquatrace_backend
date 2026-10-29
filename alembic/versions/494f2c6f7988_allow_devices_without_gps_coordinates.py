"""Allow devices without GPS coordinates.

Revision ID: 494f2c6f7988
Revises: 1cc7768dbccc
"""

from alembic import op
import sqlalchemy as sa


revision = "494f2c6f7988"
down_revision = "1cc7768dbccc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow devices to exist before their first GPS report.
    op.alter_column(
        "devices",
        "latitude",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.alter_column(
        "devices",
        "longitude",
        existing_type=sa.Float(),
        nullable=True,
    )

    # Require coordinates to be both present or both absent.
    op.create_check_constraint(
        "ck_devices_coordinates_together",
        "devices",
        "(latitude IS NULL) = (longitude IS NULL)",
    )


def downgrade() -> None:
    # Refuse to restore NOT NULL if any device lacks coordinates.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM devices
                WHERE latitude IS NULL OR longitude IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot restore NOT NULL: devices have missing coordinates';
            END IF;
        END $$;
        """
    )

    op.drop_constraint(
        "ck_devices_coordinates_together",
        "devices",
        type_="check",
    )

    op.alter_column(
        "devices",
        "latitude",
        existing_type=sa.Float(),
        nullable=False,
    )
    op.alter_column(
        "devices",
        "longitude",
        existing_type=sa.Float(),
        nullable=False,
    )

"""Move location fields to devices.

Revision ID: 1cc7768dbccc
Revises: d75bd484d00b
"""

from alembic import op
import sqlalchemy as sa


revision = "1cc7768dbccc"
down_revision = "d75bd484d00b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve original device-to-location mappings for downgrade.
    op.create_table(
        "device_location_migration_backup",
        sa.Column("device_id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("location_id", sa.UUID(), nullable=False),
    )

    op.execute(
        """
        INSERT INTO device_location_migration_backup (device_id, location_id)
        SELECT device_id, location_id
        FROM devices
        """
    )

    # Add the new fields before copying existing location data.
    op.add_column(
        "devices",
        sa.Column("latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("address", sa.String(255), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("name", sa.String(255), nullable=True),
    )

    # Copy the data from each device's existing location.
    op.execute(
        """
        UPDATE devices AS d
        SET latitude = l.latitude,
            longitude = l.longitude,
            address = l.address,
            name = l.name
        FROM locations AS l
        WHERE d.location_id = l.location_id
        """
    )

    # Abort if any device could not be migrated.
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
                    'Cannot migrate devices: missing location coordinates';
            END IF;
        END
        $$;
        """
    )

    # Enforce required coordinates.
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

    # Remove the old foreign key and column.
    op.drop_constraint(
        "devices_location_id_fkey",
        "devices",
        type_="foreignkey",
    )
    op.drop_column("devices", "location_id")

    # Validate coordinate ranges.
    op.create_check_constraint(
        "ck_devices_latitude",
        "devices",
        "latitude BETWEEN -90 AND 90",
    )
    op.create_check_constraint(
        "ck_devices_longitude",
        "devices",
        "longitude BETWEEN -180 AND 180",
    )

    # Match the model's user_id index.
    device_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("devices")
    }

    if "ix_devices_user_id" not in device_indexes:
        op.create_index(
            "ix_devices_user_id",
            "devices",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    # Restore the old location_id column.
    op.add_column(
        "devices",
        sa.Column("location_id", sa.UUID(), nullable=True),
    )

    # Restore the exact original mappings.
    op.execute(
        """
        UPDATE devices AS d
        SET location_id = b.location_id
        FROM device_location_migration_backup AS b
        WHERE d.device_id = b.device_id
        """
    )

    # Do not proceed if any device lacks its original mapping.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM devices
                WHERE location_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade: original location mapping missing';
            END IF;
        END
        $$;
        """
    )

    op.alter_column(
        "devices",
        "location_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    op.create_foreign_key(
        "devices_location_id_fkey",
        "devices",
        "locations",
        ["location_id"],
        ["location_id"],
    )

    # Remove the new index and constraints.
    op.drop_index("ix_devices_user_id", table_name="devices")

    op.drop_constraint(
        "ck_devices_longitude",
        "devices",
        type_="check",
    )
    op.drop_constraint(
        "ck_devices_latitude",
        "devices",
        type_="check",
    )

    # Remove the fields introduced by this migration.
    op.drop_column("devices", "name")
    op.drop_column("devices", "address")
    op.drop_column("devices", "longitude")
    op.drop_column("devices", "latitude")

    # Remove the saved mappings only after restoration succeeds.
    op.drop_table("device_location_migration_backup")

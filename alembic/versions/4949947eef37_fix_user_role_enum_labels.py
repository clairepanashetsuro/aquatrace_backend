"""Fix PostgreSQL user_role enum labels."""

from alembic import op
import sqlalchemy as sa

revision = "4949947eef37"
down_revision = "34fbd149345d"
branch_labels = None
depends_on = None


def _get_labels():
    result = op.get_bind().execute(
        sa.text("""
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'user_role'
        """)
    )
    return set(result.scalars())


def upgrade():
    labels = _get_labels()

    for old, new in [
        ("Water quality officer", "WATER_QUALITY_OFFICER"),
        ("Field officer", "FIELD_OFFICER"),
        ("Admin", "ADMIN"),
    ]:
        if old in labels and new not in labels:
            op.execute(
                sa.text(
                    f"ALTER TYPE user_role RENAME VALUE '{old}' TO '{new}'"
                )
            )
            labels.remove(old)
            labels.add(new)


def downgrade():
    labels = _get_labels()

    for old, new in [
        ("WATER_QUALITY_OFFICER", "Water quality officer"),
        ("FIELD_OFFICER", "Field officer"),
        ("ADMIN", "Admin"),
    ]:
        if old in labels and new not in labels:
            op.execute(
                sa.text(
                    f"ALTER TYPE user_role RENAME VALUE '{old}' TO '{new}'"
                )
            )
            labels.remove(old)
            labels.add(new)

"""Fix PostgreSQL user_status enum labels."""

from alembic import op
import sqlalchemy as sa

revision = "add225b271f2"
down_revision = "4949947eef37"
branch_labels = None
depends_on = None


def _get_labels():
    result = op.get_bind().execute(
        sa.text("""
            SELECT e.enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'user_status'
        """)
    )
    return set(result.scalars())


def upgrade():
    labels = _get_labels()

    for old, new in [
        ("active", "ACTIVE"),
        ("inactive", "INACTIVE"),
    ]:
        if old in labels and new not in labels:
            op.execute(
                sa.text(
                    f"ALTER TYPE user_status RENAME VALUE '{old}' TO '{new}'"
                )
            )
            labels.remove(old)
            labels.add(new)


def downgrade():
    labels = _get_labels()

    for old, new in [
        ("ACTIVE", "active"),
        ("INACTIVE", "inactive"),
    ]:
        if old in labels and new not in labels:
            op.execute(
                sa.text(
                    f"ALTER TYPE user_status RENAME VALUE '{old}' TO '{new}'"
                )
            )
            labels.remove(old)
            labels.add(new)

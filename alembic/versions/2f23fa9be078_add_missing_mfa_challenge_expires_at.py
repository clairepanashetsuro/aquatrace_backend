"""add missing mfa_challenge_expires_at

Revision ID: 2f23fa9be078
Revises: b57d7ede223f
Create Date: 2026-10-21 20:05:39.768650

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2f23fa9be078"
down_revision: Union[str, Sequence[str], None] = "b57d7ede223f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "mfa_challenge_expires_at" not in existing:
        op.add_column(
            "users",
            sa.Column(
                "mfa_challenge_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "mfa_challenge_expires_at")

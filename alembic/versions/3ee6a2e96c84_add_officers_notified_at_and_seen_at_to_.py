"""add officers_notified_at and seen_at to alerts

Revision ID: 3ee6a2e96c84
Revises: 497b62447577
Create Date: 2026-10-20 22:47:58.511096

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3ee6a2e96c84"
down_revision: Union[str, Sequence[str], None] = "956315be63d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("officers_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts", sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("alerts", "seen_at")
    op.drop_column("alerts", "officers_notified_at")

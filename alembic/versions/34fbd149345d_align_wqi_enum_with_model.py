"""align wqi enum with model

Revision ID: 34fbd149345d
Revises: 2cb53f290225
Create Date: 2026-10-28 17:28:09.890956


"""

from typing import Sequence, Union

from alembic import op

revision: str = "34fbd149345d"
down_revision: Union[str, None] = "2cb53f290225"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE wqi_status ADD VALUE IF NOT EXISTS 'excellent'")
    op.execute("ALTER TYPE wqi_status ADD VALUE IF NOT EXISTS 'regular'")
    op.execute("ALTER TYPE wqi_status ADD VALUE IF NOT EXISTS 'very_poor'")


def downgrade() -> None:
    pass

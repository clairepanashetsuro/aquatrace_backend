"""make location address nullable

Revision ID: b57d7ede223f
Revises: f6bbe32960c5
Create Date: 2026-10-21 15:01:05.970871

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b57d7ede223f"
down_revision: Union[str, Sequence[str], None] = "f6bbe32960c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "locations",
        "address",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "locations",
        "address",
        existing_type=sa.String(length=255),
        nullable=False,
    )

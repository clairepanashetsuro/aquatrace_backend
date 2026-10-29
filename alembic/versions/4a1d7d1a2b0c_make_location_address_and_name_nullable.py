"""make location address and name nullable

Revision ID: 4a1d7d1a2b0c
Revises: 51c8affa8676
Create Date: 2026-10-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a1d7d1a2b0c"
down_revision: Union[str, Sequence[str], None] = "51c8affa8676"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "locations",
        "address",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "locations",
        "name",
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
    op.alter_column(
        "locations",
        "name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

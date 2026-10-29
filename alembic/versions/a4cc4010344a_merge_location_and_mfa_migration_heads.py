"""merge location and MFA migration heads

Revision ID: a4cc4010344a
Revises: 4a1d7d1a2b0c, b57d7ede223f
Create Date: 2026-10-23 08:02:44.416037

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "a4cc4010344a"
down_revision: Union[str, Sequence[str], None] = ("4a1d7d1a2b0c", "b57d7ede223f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

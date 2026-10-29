"""merge migration heads

Revision ID: a7e2190dd4ac
Revises: 2f23fa9be078, e4e849f201c7
Create Date: 2026-10-23 23:45:44.404325

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "a7e2190dd4ac"
down_revision: Union[str, Sequence[str], None] = ("2f23fa9be078", "e4e849f201c7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

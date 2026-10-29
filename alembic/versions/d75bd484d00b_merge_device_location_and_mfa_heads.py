"""Merge device location and MFA heads.

Revision ID: d75bd484d00b
Revises: a4cc4010344a, 2f23fa9be078
Create Date: 2026-10-24 00:17:39.780325
"""

from typing import Sequence, Union

# Revision identifiers used by Alembic.
revision: str = "d75bd484d00b"
down_revision: Union[str, Sequence[str], None] = (
    "a4cc4010344a",
    "2f23fa9be078",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge the device-location and MFA migration branches."""
    pass


def downgrade() -> None:
    """Merge revision has no schema changes to reverse."""
    pass

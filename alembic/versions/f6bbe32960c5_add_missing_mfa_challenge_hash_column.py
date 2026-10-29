"""add missing MFA challenge hash column

Revision ID: f6bbe32960c5
Revises: e16d112491dd
Create Date: 2026-10-21 14:57:47.599865

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6bbe32960c5"
down_revision: Union[str, Sequence[str], None] = "e16d112491dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("users")
    }

    if "mfa_challenge_hash" not in user_columns:
        op.add_column(
            "users",
            sa.Column("mfa_challenge_hash", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("users", "mfa_challenge_hash")

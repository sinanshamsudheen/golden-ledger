"""Add custom_prompt column to users table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-06 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("custom_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "custom_prompt")

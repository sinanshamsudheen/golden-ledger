"""Add deal_name and version_status columns to documents.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-04 00:00:00.000000 UTC

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("deal_name", sa.String(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("version_status", sa.String(), nullable=False, server_default="current"),
    )


def downgrade() -> None:
    op.drop_column("documents", "version_status")
    op.drop_column("documents", "deal_name")

"""Add folder_ids JSONB column to users table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-06 00:00:00.000000 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("folder_ids", JSONB(), nullable=True))
    # Migrate existing folder_id into the new column
    op.execute("""
        UPDATE users
        SET folder_ids = jsonb_build_array(
            jsonb_build_object('id', folder_id, 'label', folder_id)
        )
        WHERE folder_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("users", "folder_ids")

"""Change documents.file_id unique constraint from global to per-user.

Previously file_id was globally unique across all users, preventing two users
from holding a record for the same Drive file.  This blocks the copy-user-data
script from storing real Drive file IDs for a second user — forcing it to use
suffixed IDs that break the worker's checksum / file_id dedup logic.

After this migration:
  • The global unique index on file_id is removed.
  • A composite unique constraint on (user_id, file_id) is added.
  • The worker's known_ids dedup is already filtered by user_id, so behaviour
    is unchanged for normal runs.
  • Two different users can now hold records for the same public Drive file with
    the real file_id, and the worker will correctly skip them for each user.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-06 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old globally-unique index on file_id
    op.drop_index("ix_documents_file_id", table_name="documents")

    # Add composite unique constraint: one record per (user, drive file)
    op.create_index(
        "ix_documents_user_file_id",
        "documents",
        ["user_id", "file_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_file_id", table_name="documents")
    op.create_index("ix_documents_file_id", "documents", ["file_id"], unique=True)

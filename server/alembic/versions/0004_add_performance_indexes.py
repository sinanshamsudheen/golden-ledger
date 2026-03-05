"""Add performance indexes on documents for scale.

Without these, every query that filters by user_id, status, doc_type, or
checksum does a full table scan — fine at 100 rows, painful at 100k+.

Indexes added
-------------
ix_documents_user_id           (user_id)
    — prerequisite for every user-scoped query in the system

ix_documents_user_status       (user_id, status)
    — get_latest_documents_per_type: WHERE user_id=? AND status IN (...)
    — all_documents route:          WHERE user_id=? AND status IN (...)

ix_documents_user_checksum     (user_id, checksum) WHERE checksum IS NOT NULL
    — dedup bulk query in get_unprocessed_files

ix_documents_deal_type         (deal_id, doc_type) WHERE deal_id IS NOT NULL
    — get_latest_documents_per_type GROUP BY (deal_id, doc_type)

ix_documents_user_folder_type  (user_id, folder_path, doc_type)
    — get_latest_documents_per_type dealless GROUP BY (folder_path, doc_type)
    — _mark_superseded_versions Pass B filter

ix_documents_user_type_version (user_id, doc_type, version_status)
    — _mark_superseded_versions: WHERE user_id=? doc_type=? version_status='current'

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-05 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_documents_user_id",
        "documents",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_documents_user_status",
        "documents",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_documents_user_checksum",
        "documents",
        ["user_id", "checksum"],
        unique=False,
        postgresql_where=sa.text("checksum IS NOT NULL"),
    )
    op.create_index(
        "ix_documents_deal_type",
        "documents",
        ["deal_id", "doc_type"],
        unique=False,
        postgresql_where=sa.text("deal_id IS NOT NULL"),
    )
    op.create_index(
        "ix_documents_user_folder_type",
        "documents",
        ["user_id", "folder_path", "doc_type"],
        unique=False,
    )
    op.create_index(
        "ix_documents_user_type_version",
        "documents",
        ["user_id", "doc_type", "version_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_type_version", table_name="documents")
    op.drop_index("ix_documents_user_folder_type", table_name="documents")
    op.drop_index("ix_documents_deal_type", table_name="documents")
    op.drop_index("ix_documents_user_checksum", table_name="documents")
    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")

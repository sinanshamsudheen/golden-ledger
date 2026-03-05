"""Add vectorizer fields to documents and deals.

documents
---------
  vectorizer_doc_id  — the doc_id assigned by Invitus AI Insights after a
                       successful ingestion job. Null until the pipeline runs.

deals
-----
  investment_type  — Fund | Direct | Co-Investment (from Analytical endpoint)
  deal_status      — accepted | rejected           (from Analytical endpoint)
  deal_reason      — 1-2 sentence IC rationale     (from Analytical endpoint)
  vectorizer_job_id — external pipeline job ID     (for debugging / re-runs)

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-06 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── documents ─────────────────────────────────────────────────────────────
    op.add_column(
        "documents",
        sa.Column("vectorizer_doc_id", sa.String(), nullable=True),
    )

    # ── deals ─────────────────────────────────────────────────────────────────
    op.add_column("deals", sa.Column("investment_type", sa.String(), nullable=True))
    op.add_column("deals", sa.Column("deal_status", sa.String(), nullable=True))
    op.add_column("deals", sa.Column("deal_reason", sa.Text(), nullable=True))
    op.add_column("deals", sa.Column("vectorizer_job_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "vectorizer_job_id")
    op.drop_column("deals", "deal_reason")
    op.drop_column("deals", "deal_status")
    op.drop_column("deals", "investment_type")
    op.drop_column("documents", "vectorizer_doc_id")

"""Add deals table and migrate documents to use deal_id FK.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-04 00:00:00.000000 UTC

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create deals table
    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_deals_user_name_key"),
    )
    op.create_index(op.f("ix_deals_id"), "deals", ["id"], unique=False)
    op.create_index(op.f("ix_deals_name_key"), "deals", ["name_key"], unique=False)

    # Add new columns to documents
    op.add_column("documents", sa.Column("deal_id", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("folder_path", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_documents_deal_id", "documents", "deals", ["deal_id"], ["id"]
    )
    op.create_index(op.f("ix_documents_deal_id"), "documents", ["deal_id"], unique=False)

    # Drop the old plain-string deal_name column
    op.drop_column("documents", "deal_name")


def downgrade() -> None:
    op.add_column("documents", sa.Column("deal_name", sa.String(), nullable=True))
    op.drop_index(op.f("ix_documents_deal_id"), table_name="documents")
    op.drop_constraint("fk_documents_deal_id", "documents", type_="foreignkey")
    op.drop_column("documents", "folder_path")
    op.drop_column("documents", "deal_id")
    op.drop_index(op.f("ix_deals_name_key"), table_name="deals")
    op.drop_index(op.f("ix_deals_id"), table_name="deals")
    op.drop_table("deals")

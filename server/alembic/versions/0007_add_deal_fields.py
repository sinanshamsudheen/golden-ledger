"""Add deal_fields table.

Stores per-deal structured field values extracted by the ExtractFields API
(investment type-specific fields: IRR, MOIC, fund size, geography, etc.).
Rows are delete-and-reinsert on every pipeline run so they always reflect
the latest documents.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-05 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deal_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("field_label", sa.String(), nullable=True),
        sa.Column("field_type", sa.String(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_formatted", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", "field_name", name="uq_deal_fields_deal_field"),
    )
    op.create_index("ix_deal_fields_id", "deal_fields", ["id"])
    op.create_index("ix_deal_fields_deal_id", "deal_fields", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_deal_fields_deal_id", table_name="deal_fields")
    op.drop_index("ix_deal_fields_id", table_name="deal_fields")
    op.drop_table("deal_fields")

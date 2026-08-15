"""Add composite index on prices source_id and source_name.

Revision ID: d3a1f8c90211
Revises: c4e8a1b92f03
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d3a1f8c90211"
down_revision: Union[str, None] = "c4e8a1b92f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_prices_source_id_source_name",
        "prices",
        ["source_id", "source_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_prices_source_id_source_name", table_name="prices")

"""Add missing auction house enum values.

Revision ID: c4e8a1b92f03
Revises: f72066955838
Create Date: 2026-07-03
"""

from alembic import op

revision = "c4e8a1b92f03"
down_revision = "f72066955838"
branch_labels = None
depends_on = None

NEW_VALUES = [
    "WHISKY_AUCTION_UK",
    "WHISKYAUCTION_COM",
    "WHISKY_HAMMER",
    "WHISKY_HUNTER",
    "BOTTLE_BLUE_BOOK",
    "WHISKYSTATS",
    "RARE_WHISKY_101",
]


def upgrade() -> None:
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE auctionhouse ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass

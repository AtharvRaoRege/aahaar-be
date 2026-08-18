"""reviews and review QR kind

Revision ID: d7a1c4e90b12
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 10:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7a1c4e90b12"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("improvement", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_reviews_order_id"),
    )
    op.create_index("ix_reviews_restaurant_id", "reviews", ["restaurant_id"])
    op.create_index("ix_reviews_order_id", "reviews", ["order_id"])

    op.add_column(
        "qr_codes",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="TABLE"),
    )
    op.create_index("ix_qr_codes_kind", "qr_codes", ["kind"])
    op.create_index(
        "uq_qr_codes_review_per_restaurant",
        "qr_codes",
        ["restaurant_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'REVIEW'"),
    )


def downgrade() -> None:
    op.drop_index("uq_qr_codes_review_per_restaurant", table_name="qr_codes")
    op.drop_index("ix_qr_codes_kind", table_name="qr_codes")
    op.drop_column("qr_codes", "kind")
    op.drop_index("ix_reviews_order_id", table_name="reviews")
    op.drop_index("ix_reviews_restaurant_id", table_name="reviews")
    op.drop_table("reviews")

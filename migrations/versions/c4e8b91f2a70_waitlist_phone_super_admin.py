"""waitlist phone super admin and venue kind

Revision ID: c4e8b91f2a70
Revises: 9f4c2a81b0d3
Create Date: 2026-08-16 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8b91f2a70"
down_revision: Union[str, None] = "9f4c2a81b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column(
                "approval_status",
                sa.String(length=20),
                nullable=False,
                server_default="APPROVED",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_super_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("waitlist_notified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_users_approval_status"),
            ["approval_status"],
            unique=False,
        )

    with op.batch_alter_table("restaurants", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "venue_kind",
                sa.String(length=20),
                nullable=False,
                server_default="RESTAURANT",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("restaurants", schema=None) as batch_op:
        batch_op.drop_column("venue_kind")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_approval_status"))
        batch_op.drop_column("waitlist_notified_at")
        batch_op.drop_column("is_super_admin")
        batch_op.drop_column("approval_status")
        batch_op.drop_column("phone")

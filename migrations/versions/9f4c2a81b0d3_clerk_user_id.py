"""clerk_user_id and optional password for Google SSO users

Revision ID: 9f4c2a81b0d3
Revises: 140ff6d406e9
Create Date: 2026-08-16 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4c2a81b0d3"
down_revision: Union[str, None] = "140ff6d406e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("clerk_user_id", sa.String(length=64), nullable=True))
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch_op.create_index(
            batch_op.f("ix_users_clerk_user_id"),
            ["clerk_user_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_clerk_user_id"))
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        batch_op.drop_column("clerk_user_id")

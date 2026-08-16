"""session id for single-device login

Revision ID: a1b2c3d4e5f6
Revises: c4e8b91f2a70
Create Date: 2026-08-16 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c4e8b91f2a70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "session_id",
                sa.Uuid(),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            )
        )
        batch_op.create_index("ix_users_session_id", ["session_id"])


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_session_id")
        batch_op.drop_column("session_id")

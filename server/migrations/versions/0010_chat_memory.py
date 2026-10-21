"""小媒的长期聊天记忆：account.chat_memory（早的聊天滚动压成要点）

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('account', schema=None) as b:
        b.add_column(sa.Column('chat_memory', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('account') as b:
        b.drop_column('chat_memory')

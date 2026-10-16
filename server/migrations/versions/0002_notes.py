"""notes：管家的运营笔记

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('note',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('account_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('note', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_note_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_note_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('note', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_note_user_id'))
        batch_op.drop_index(batch_op.f('ix_note_account_id'))
    op.drop_table('note')

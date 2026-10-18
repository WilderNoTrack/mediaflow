"""benchmark：对标账号复刻；topic.reference

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

S = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table('benchmark',
    sa.Column('id', S(), nullable=False),
    sa.Column('user_id', S(), nullable=False),
    sa.Column('account_id', S(), nullable=False),
    sa.Column('platform', S(), nullable=False),
    sa.Column('target', S(), nullable=False),
    sa.Column('theme', S(), nullable=False),
    sa.Column('creator_name', S(), nullable=False),
    sa.Column('creator_url', S(), nullable=False),
    sa.Column('creator_info', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('analyzing', 'ready', 'failed', name='benchmarkstatus'), nullable=False),
    sa.Column('playbook', sa.JSON(), nullable=False),
    sa.Column('plan', sa.JSON(), nullable=False),
    sa.Column('samples', sa.JSON(), nullable=False),
    sa.Column('error', S(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('benchmark', schema=None) as b:
        b.create_index(b.f('ix_benchmark_account_id'), ['account_id'], unique=False)
        b.create_index(b.f('ix_benchmark_user_id'), ['user_id'], unique=False)
    with op.batch_alter_table('topic', schema=None) as b:
        b.add_column(sa.Column('reference', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('topic', schema=None) as b:
        b.drop_column('reference')
    with op.batch_alter_table('benchmark', schema=None) as b:
        b.drop_index(b.f('ix_benchmark_user_id'))
        b.drop_index(b.f('ix_benchmark_account_id'))
    op.drop_table('benchmark')

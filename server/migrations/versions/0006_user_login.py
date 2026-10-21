"""user：在线版登录（用户名、密码、管理员、停用）

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 不用 batch 模式：SQLite 的 batch 会重建 user 表，已有数据（外键引用 user）时会失败。
    # 直接 ADD COLUMN（都有常量默认值）+ CREATE INDEX 就够了。
    op.add_column('user', sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('user', sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.add_column('user', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user', sa.Column('disabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('user', sa.Column('last_login_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    op.create_index('ix_user_username', 'user', ['username'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as b:
        b.drop_index('ix_user_username')
        for c in ('last_login_at', 'token_version', 'disabled', 'is_admin', 'password_hash', 'username'):
            b.drop_column(c)

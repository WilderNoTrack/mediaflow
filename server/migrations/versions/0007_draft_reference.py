"""draft.reference：这篇照着哪篇帖子写、出图；draftimage.ref_path：每张图照着原帖哪一张出

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 直接 ADD COLUMN（不用 batch，避免 SQLite 重建表碰外键）
    op.add_column('draft', sa.Column('reference', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('draftimage', sa.Column('ref_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('draftimage') as b:
        b.drop_column('ref_path')
    with op.batch_alter_table('draft') as b:
        b.drop_column('reference')

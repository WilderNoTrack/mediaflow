"""账号配图模板 + 出图自检：account.visual、draft.image_mold、draftimage.page_type / review

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('account', schema=None) as b:
        b.add_column(sa.Column('visual', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('draft', sa.Column('image_mold', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    with op.batch_alter_table('draftimage', schema=None) as b:
        b.add_column(sa.Column('page_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        b.add_column(sa.Column('review', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('draftimage') as b:
        b.drop_column('review')
        b.drop_column('page_type')
    with op.batch_alter_table('draft') as b:
        b.drop_column('image_mold')
    with op.batch_alter_table('account') as b:
        b.drop_column('visual')

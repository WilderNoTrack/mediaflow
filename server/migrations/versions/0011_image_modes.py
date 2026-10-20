"""配图不止 AI 画：account.image_mode（整个账号默认怎么出图）+ draft_image.mode/made_by/layout/source

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('account', schema=None) as b:
        b.add_column(sa.Column('image_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='ai'))
    with op.batch_alter_table('draftimage', schema=None) as b:
        b.add_column(sa.Column('mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        b.add_column(sa.Column('made_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        b.add_column(sa.Column('layout', sa.JSON(), nullable=False, server_default='{}'))
        b.add_column(sa.Column('source', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('draftimage') as b:
        for c in ('source', 'layout', 'made_by', 'mode'):
            b.drop_column(c)
    with op.batch_alter_table('account') as b:
        b.drop_column('image_mode')

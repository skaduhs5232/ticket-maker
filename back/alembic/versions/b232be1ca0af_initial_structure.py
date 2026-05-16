"""initial_structure

Revision ID: b232be1ca0af
Revises: 
Create Date: 2026-05-15 21:33:29.108517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b232be1ca0af'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('project_id', sa.String(), index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )
    
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id', ondelete='CASCADE')),
        sa.Column('role', sa.String()),
        sa.Column('content', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('messages')
    op.drop_table('conversations')
    op.execute("DROP EXTENSION IF EXISTS vector")

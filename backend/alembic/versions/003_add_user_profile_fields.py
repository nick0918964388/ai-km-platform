"""Add user profile fields

Revision ID: 003_user_profile
Revises: 002_add_documents_table
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_user_profile'
down_revision: Union[str, None] = '002_add_documents_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table with profile fields
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(50), nullable=False, server_default=''),
        sa.Column('avatar_url', sa.String(255), nullable=True),
        sa.Column('account_level', sa.String(20), nullable=False, server_default='free'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Add indexes for performance
    op.create_index('idx_users_email', 'users', ['email'], unique=True)
    op.create_index('idx_users_id', 'users', ['id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_users_id', table_name='users')
    op.drop_index('idx_users_email', table_name='users')

    # Drop users table
    op.drop_table('users')

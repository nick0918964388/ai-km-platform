"""Add documents table

Revision ID: 002_documents
Revises: 001_initial
Create Date: 2026-02-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_documents'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('doc_type', sa.String(20), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False, default=0),
        sa.Column('chunk_count', sa.Integer(), nullable=False, default=0),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('idx_documents_uploaded_at', 'documents', ['uploaded_at'])
    op.create_index('idx_documents_doc_type', 'documents', ['doc_type'])

def downgrade() -> None:
    op.drop_index('idx_documents_doc_type')
    op.drop_index('idx_documents_uploaded_at')
    op.drop_table('documents')

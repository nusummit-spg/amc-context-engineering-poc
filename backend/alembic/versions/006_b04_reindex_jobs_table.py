"""B04: Create reindex_jobs table

Revision ID: 006_b04_reindex_jobs
Revises: 005_b03_corrected_value
Create Date: 2026-11-05 11:00:00.000000

Wave 1.3 Batch B (B04): Reindex Verification
- Creates reindex_jobs table to track vector store reindex operations
- Stores verification receipts for each reindex job
- Closes C-10 (reindex verification) integrity gate
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006_b04_reindex_jobs'
down_revision = '005_b03_corrected_value'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reindex_jobs table."""
    
    op.create_table(
        'reindex_jobs',
        sa.Column('job_id', sa.String(length=64), nullable=False, comment='B04: Unique reindex job identifier'),
        sa.Column('proposal_id', sa.String(length=64), nullable=True, comment='Related repair proposal'),
        sa.Column('document_ids', sa.JSON(), nullable=True, comment='Documents to reindex'),
        sa.Column('document_count', sa.Integer(), nullable=False, default=0, comment='Number of documents'),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending', comment='Job status: pending/running/completed/failed'),
        sa.Column('started_at', sa.String(length=40), nullable=False, comment='ISO timestamp when job started'),
        sa.Column('completed_at', sa.String(length=40), nullable=True, comment='ISO timestamp when job completed'),
        sa.Column('verified', sa.Boolean(), nullable=False, default=False, comment='B04: Whether reindex was verified'),
        sa.Column('verification_receipt', sa.JSON(), nullable=True, comment='B04: Immutable verification receipt'),
        sa.Column('error', sa.Text(), nullable=True, comment='Error message if job failed'),
        sa.PrimaryKeyConstraint('job_id'),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name='ck_reindex_status')
    )
    
    # Create indexes for common queries
    op.create_index('idx_reindex_proposal_id', 'reindex_jobs', ['proposal_id'])
    op.create_index('idx_reindex_status', 'reindex_jobs', ['status'])
    op.create_index('idx_reindex_started_at', 'reindex_jobs', ['started_at'])


def downgrade() -> None:
    """Drop reindex_jobs table."""
    
    op.drop_index('idx_reindex_started_at', table_name='reindex_jobs')
    op.drop_index('idx_reindex_status', table_name='reindex_jobs')
    op.drop_index('idx_reindex_proposal_id', table_name='reindex_jobs')
    op.drop_table('reindex_jobs')

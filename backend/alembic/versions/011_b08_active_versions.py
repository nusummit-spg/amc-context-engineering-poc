"""B02: Create active_versions table for immutable FAISS generation tracking

Revision ID: 011_b08_active_versions
Revises: 010_b07_publication_effects
Create Date: 2026-11-06 00:00:00.000000

Wave 1.7 Batch B (B02): Immutable FAISS Generation Build
- Creates active_versions table for versioned index tracking
- Enables atomic CAS pointer switches between generations
- Supports rollback to previous generation with verified receipt
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_b08_active_versions'
down_revision = '010_b07_publication_effects'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create active_versions table."""
    
    op.create_table(
        'active_versions',
        sa.Column('version_id', sa.String(length=64), nullable=False, comment='B02: Unique version identifier'),
        sa.Column('tenant', sa.String(length=128), nullable=False, comment='Multi-tenant isolation'),
        sa.Column('corpus_namespace', sa.String(length=64), nullable=False, comment='Namespace: graph, vector_faiss'),
        sa.Column('version', sa.Integer(), nullable=False, comment='Generation version number'),
        sa.Column('generation_id', sa.String(length=64), nullable=False, comment='FAISS generation identifier'),
        sa.Column('status', sa.String(length=20), nullable=False, default='staged', comment='Status: staged, active, retired'),
        sa.Column('source_hash', sa.String(length=64), nullable=False, comment='SHA-256 hash of source data'),
        sa.Column('source_version', sa.String(length=64), nullable=False, comment='Source document version'),
        sa.Column('row_count', sa.Integer(), nullable=False, comment='Number of rows/documents in generation'),
        sa.Column('created_at', sa.String(length=40), nullable=False, comment='ISO timestamp when generation created'),
        sa.Column('activated_at', sa.String(length=40), nullable=True, comment='ISO timestamp when activated'),
        sa.Column('retired_at', sa.String(length=40), nullable=True, comment='ISO timestamp when retired'),
        sa.Column('prev_version_id', sa.String(length=64), nullable=True, comment='Previous version for rollback'),
        sa.Column('next_version_id', sa.String(length=64), nullable=True, comment='Next version for forward rollback'),
        sa.Column('fencing_token', sa.String(length=64), nullable=False, comment='CAS fencing token for concurrency control'),
        sa.Column('verified', sa.Boolean(), nullable=False, default=False, comment='Whether generation was verified'),
        sa.PrimaryKeyConstraint('version_id'),
        sa.CheckConstraint("status IN ('staged', 'active', 'retired')", name='ck_active_version_status')
    )
    
    # Create indexes for active_versions
    op.create_index('idx_active_version_tenant', 'active_versions', ['tenant', 'corpus_namespace'])
    op.create_index('idx_active_version_status', 'active_versions', ['status'])
    op.create_index('idx_active_version_source', 'active_versions', ['source_hash', 'source_version'])
    op.create_index('idx_active_version_fencing', 'active_versions', ['fencing_token'])


def downgrade() -> None:
    """Drop active_versions table."""
    
    # Drop indexes
    op.drop_index('idx_active_version_fencing', table_name='active_versions')
    op.drop_index('idx_active_version_source', table_name='active_versions')
    op.drop_index('idx_active_version_status', table_name='active_versions')
    op.drop_index('idx_active_version_tenant', table_name='active_versions')
    
    # Drop table
    op.drop_table('active_versions')

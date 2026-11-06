"""B01: Create publication_effects table for durable effect tracking

Revision ID: 010_b07_publication_effects
Revises: 009_b06_publication_intents
Create Date: 2026-11-06 00:00:00.000000

Wave 1.7 Batch B (B01): Durable Graph/Vector Staging and Effects
- Creates publication_effects table for per-effect tracking
- Enables exact-ID snapshot and immutable FAISS generations
- Supports verified Neo4j/FAISS mutation and rollback
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010_b07_publication_effects'
down_revision = '009_b06_publication_intents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create publication_effects table."""
    
    op.create_table(
        'publication_effects',
        sa.Column('effect_id', sa.String(length=64), nullable=False, comment='B01: Unique effect identifier'),
        sa.Column('intent_id', sa.String(length=64), nullable=False, comment='Reference to publication intent'),
        sa.Column('effect_kind', sa.String(length=32), nullable=False, comment='Effect kind: graph_mutation, graph_delete, vector_add, vector_delete'),
        sa.Column('effect_target', sa.String(length=128), nullable=False, comment='Target entity or chunk ID'),
        sa.Column('effect_revision', sa.Integer(), nullable=False, default=1, comment='Effect revision number for idempotency'),
        sa.Column('preimage_hash', sa.String(length=64), nullable=True, comment='SHA-256 hash of preimage (for rollback verification)'),
        sa.Column('preimage_snapshot', sa.JSON(), nullable=True, comment='Snapshot of preimage state (for rollback)'),
        sa.Column('postimage_hash', sa.String(length=64), nullable=True, comment='SHA-256 hash of postimage (for verification)'),
        sa.Column('postimage_snapshot', sa.JSON(), nullable=True, comment='Snapshot of postimage state (for readback verification)'),
        sa.Column('applied_at', sa.String(length=40), nullable=True, comment='ISO timestamp when effect was applied'),
        sa.Column('observed_at', sa.String(length=40), nullable=True, comment='ISO timestamp when effect was observed via readback'),
        sa.Column('verified', sa.Boolean(), nullable=False, default=False, comment='Whether effect was verified via readback'),
        sa.Column('result_status', sa.String(length=20), nullable=False, default='pending', comment='Status: pending, applied, verified, failed, conflicted'),
        sa.Column('error', sa.Text(), nullable=True, comment='Error message if failed'),
        sa.Column('tenant', sa.String(length=128), nullable=False, default='default', comment='Multi-tenant isolation'),
        sa.Column('fencing_token', sa.String(length=64), nullable=True, comment='CAS fencing token for concurrency control'),
        sa.Column('source_version', sa.String(length=64), nullable=True, comment='Source version at effect time'),
        sa.Column('created_at', sa.String(length=40), nullable=False, comment='ISO timestamp when effect recorded'),
        sa.PrimaryKeyConstraint('effect_id'),
        sa.CheckConstraint("effect_kind IN ('graph_mutation', 'graph_delete', 'vector_add', 'vector_delete')", name='ck_effect_kind'),
        sa.CheckConstraint("result_status IN ('pending', 'applied', 'verified', 'failed', 'conflicted')", name='ck_effect_status')
    )
    
    # Create indexes for publication_effects
    op.create_index('idx_effect_intent', 'publication_effects', ['intent_id'])
    op.create_index('idx_effect_kind_target', 'publication_effects', ['effect_kind', 'effect_target'])
    op.create_index('idx_effect_tenant_status', 'publication_effects', ['tenant', 'result_status'])
    op.create_index('idx_effect_created', 'publication_effects', ['created_at'])


def downgrade() -> None:
    """Drop publication_effects table."""
    
    # Drop indexes for publication_effects
    op.drop_index('idx_effect_created', table_name='publication_effects')
    op.drop_index('idx_effect_tenant_status', table_name='publication_effects')
    op.drop_index('idx_effect_kind_target', table_name='publication_effects')
    op.drop_index('idx_effect_intent', table_name='publication_effects')
    
    # Drop publication_effects table
    op.drop_table('publication_effects')

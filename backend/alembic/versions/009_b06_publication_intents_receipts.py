"""P01: Create publication_intents and publication_receipts tables

Revision ID: 009_b06_publication_intents
Revises: 008_b06_rollback_status
Create Date: 2026-11-06 00:00:00.000000

Wave 1.6 Batch P (P01): Publication Intent and Receipt Schema
- Creates publication_intents table for immutable intent tracking
- Creates publication_receipts table for durable effect evidence
- Enables cross-store invariants with preimage/postimage capture
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009_b06_publication_intents'
down_revision = '008_b06_rollback_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create publication_intents and publication_receipts tables."""
    
    # Create publication_intents table
    op.create_table(
        'publication_intents',
        sa.Column('intent_id', sa.String(length=64), nullable=False, primary_key=True, comment='P01: Unique intent identifier'),
        sa.Column('proposal_id', sa.String(length=64), nullable=False, comment='Reference to repair proposal'),
        sa.Column('approved_revision', sa.Integer(), nullable=False, comment='Version number at approval time'),
        sa.Column('tenant', sa.String(length=128), nullable=False, default='default', comment='Multi-tenant isolation'),
        sa.Column('target_entity', sa.String(length=128), nullable=False, comment='Entity being modified'),
        sa.Column('source_version', sa.String(length=64), nullable=False, comment='Source document version at publication time'),
        sa.Column('publication_type', sa.String(length=20), nullable=False, comment='Type: graph_mutation, vector_reindex, patch_activation'),
        sa.Column('payload', sa.JSON(), nullable=False, comment='Full payload for execution and verification'),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending', comment='Status: pending, approved, publishing, published, failed'),
        sa.Column('created_at', sa.String(length=40), nullable=False, comment='ISO timestamp when intent created'),
        sa.Column('approved_at', sa.String(length=40), nullable=True, comment='ISO timestamp when approved'),
        sa.Column('publishing_at', sa.String(length=40), nullable=True, comment='ISO timestamp when publishing started'),
        sa.Column('published_at', sa.String(length=40), nullable=True, comment='ISO timestamp when published'),
        sa.Column('failed_at', sa.String(length=40), nullable=True, comment='ISO timestamp when failed'),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0, comment='Number of retry attempts'),
        sa.Column('max_retries', sa.Integer(), nullable=False, default=3, comment='Maximum retry attempts'),
        sa.Column('error', sa.Text(), nullable=True, comment='Error message if failed'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'publishing', 'published', 'failed')", name='ck_publication_intent_status'),
        sa.CheckConstraint("publication_type IN ('graph_mutation', 'vector_reindex', 'patch_activation')", name='ck_publication_intent_type')
    )
    
    # Create indexes for publication_intents
    op.create_index('idx_intent_proposal_revision', 'publication_intents', ['proposal_id', 'approved_revision'])
    op.create_index('idx_intent_status_created', 'publication_intents', ['status', 'created_at'])
    op.create_index('idx_intent_tenant_entity', 'publication_intents', ['tenant', 'target_entity'])
    op.create_index('idx_intent_proposal', 'publication_intents', ['proposal_id'])
    
    # Create publication_receipts table
    op.create_table(
        'publication_receipts',
        sa.Column('receipt_id', sa.String(length=64), nullable=False, comment='P01: Unique receipt identifier'),
        sa.Column('intent_id', sa.String(length=64), nullable=False, comment='Reference to publication intent'),
        sa.Column('preimage', sa.JSON(), nullable=False, comment='Value/state before publication (for rollback)'),
        sa.Column('postimage', sa.JSON(), nullable=False, comment='Value/state after publication (for verification)'),
        sa.Column('verified_at', sa.String(length=40), nullable=False, comment='ISO timestamp of verification'),
        sa.Column('verification_method', sa.String(length=64), nullable=False, comment='Method: readback, checksum, probe_query, audit_log'),
        sa.Column('source_hash', sa.String(length=128), nullable=True, comment='Optional source document hash'),
        sa.Column('source_version', sa.String(length=64), nullable=True, comment='Optional source version'),
        sa.Column('tenant', sa.String(length=128), nullable=False, default='default', comment='Multi-tenant isolation'),
        sa.Column('signature', sa.String(length=256), nullable=True, comment='Optional cryptographic signature'),
        sa.Column('created_at', sa.String(length=40), nullable=False, comment='ISO timestamp when receipt created'),
        sa.PrimaryKeyConstraint('receipt_id'),
        sa.ForeignKeyConstraint(['intent_id'], ['publication_intents.intent_id'], name='fk_receipt_intent')
    )
    
    # Create indexes for publication_receipts
    op.create_index('idx_receipt_intent', 'publication_receipts', ['intent_id'])
    op.create_index('idx_receipt_source_hash', 'publication_receipts', ['source_hash'])
    op.create_index('idx_receipt_tenant', 'publication_receipts', ['tenant'])
    op.create_index('idx_receipt_created', 'publication_receipts', ['created_at'])


def downgrade() -> None:
    """Drop publication_intents and publication_receipts tables."""
    
    # Drop indexes for publication_receipts
    op.drop_index('idx_receipt_created', table_name='publication_receipts')
    op.drop_index('idx_receipt_tenant', table_name='publication_receipts')
    op.drop_index('idx_receipt_source_hash', table_name='publication_receipts')
    op.drop_index('idx_receipt_intent', table_name='publication_receipts')
    
    # Drop foreign key constraint on publication_receipts
    op.drop_constraint('fk_receipt_intent', 'publication_receipts', type_='foreignkey')
    
    # Drop publication_receipts table
    op.drop_table('publication_receipts')
    
    # Drop indexes for publication_intents
    op.drop_index('idx_intent_proposal', table_name='publication_intents')
    op.drop_index('idx_intent_tenant_entity', table_name='publication_intents')
    op.drop_index('idx_intent_status_created', table_name='publication_intents')
    op.drop_index('idx_intent_proposal_revision', table_name='publication_intents')
    
    # Drop publication_intents table
    op.drop_table('publication_intents')

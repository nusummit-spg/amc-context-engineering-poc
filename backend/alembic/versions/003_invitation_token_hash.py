"""003: invitation_tokens, graph_mutations, repair_proposals

Revision ID: 003_invitation_token_hash
Revises: 002_feedback_tables
Create Date: 2026-10-20 00:00:00.000000

Reconstructed baseline. See remediation/wave2_2/01_MIGRATION_HISTORY.md.
Migration 004 has down_revision = '003_invitation_token_hash'; this script
re-establishes that link with the correct tables.

Tables created: invitation_tokens, graph_mutations, repair_proposals.
"""
from alembic import op
import sqlalchemy as sa

revision = '003_invitation_token_hash'
down_revision = '002_feedback_tables'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'invitation_tokens',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('username', sa.String(128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_from_ip', sa.String(45), nullable=True),
        sa.Column('redemption_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_inv_username', 'invitation_tokens', ['username'])
    op.create_index('idx_inv_expires', 'invitation_tokens', ['expires_at'])

    op.create_table(
        'graph_mutations',
        sa.Column('mutation_id', sa.String(64), primary_key=True),
        sa.Column('proposal_id', sa.String(64), nullable=True),
        sa.Column('mutation_cypher', sa.Text(), nullable=True),
        sa.Column('affected_nodes', sa.JSON(), nullable=True),
        sa.Column('applied_at', sa.String(40), nullable=False),
        sa.Column('applied_by', sa.String(64), nullable=False, server_default='promotion_service'),
        sa.Column('success', sa.Boolean(), server_default=sa.true()),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('idx_mutation_proposal', 'graph_mutations', ['proposal_id'])
    op.create_index('idx_mutation_applied_at', 'graph_mutations', ['applied_at'])

    op.create_table(
        'repair_proposals',
        sa.Column('proposal_id', sa.String(64), primary_key=True),
        sa.Column('unified_record_ref', sa.String(64),
                  sa.ForeignKey('unified_evaluation_records.response_id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('proposal_type', sa.String(20), nullable=False),
        sa.Column('entity_id', sa.String(128), nullable=True),
        sa.Column('attribute', sa.String(64), nullable=True),
        sa.Column('mutation_cypher', sa.Text(), nullable=True),
        sa.Column('affected_nodes', sa.JSON(), nullable=True),
        sa.Column('document_ids', sa.JSON(), nullable=True),
        sa.Column('reindex_required', sa.Boolean(), server_default=sa.false()),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('reviewed_at', sa.String(40), nullable=True),
        sa.Column('reviewed_by', sa.String(64), nullable=True),
        sa.Column('applied_at', sa.String(40), nullable=True),
        sa.Column('regression_score', sa.Float(), nullable=True),
        sa.CheckConstraint("proposal_type IN ('vector','graph')", name='ck_proposal_type'),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','applied')",
            name='ck_proposal_status'),
        sa.CheckConstraint('confidence BETWEEN 0.0 AND 1.0', name='ck_proposal_confidence'),
    )
    op.create_index('idx_proposal_unified', 'repair_proposals', ['unified_record_ref'])
    op.create_index('idx_proposal_entity', 'repair_proposals', ['entity_id'])
    op.create_index('idx_proposal_status', 'repair_proposals', ['status'])
    op.create_index('idx_proposal_status_conf', 'repair_proposals', ['status', 'confidence'])
    op.create_index('idx_proposal_created', 'repair_proposals', ['created_at'])

def downgrade() -> None:
    op.drop_index('idx_proposal_created', table_name='repair_proposals')
    op.drop_index('idx_proposal_status_conf', table_name='repair_proposals')
    op.drop_index('idx_proposal_status', table_name='repair_proposals')
    op.drop_index('idx_proposal_entity', table_name='repair_proposals')
    op.drop_index('idx_proposal_unified', table_name='repair_proposals')
    op.drop_table('repair_proposals')
    op.drop_index('idx_mutation_applied_at', table_name='graph_mutations')
    op.drop_index('idx_mutation_proposal', table_name='graph_mutations')
    op.drop_table('graph_mutations')
    op.drop_index('idx_inv_expires', table_name='invitation_tokens')
    op.drop_index('idx_inv_username', table_name='invitation_tokens')
    op.drop_table('invitation_tokens')
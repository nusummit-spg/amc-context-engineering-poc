"""Protect the empty-authority first-publication race (Wave 3.1).

Revision ID: 014_publication_scope_claim_v31
Revises: 013_active_receipt_authority_v28

Never auto-backfill an in-flight claim from guesses. Existing active receipts
are not changed; the first future publication/rollback creates a scope row.
"""
from alembic import op
import sqlalchemy as sa

revision = '014_publication_scope_claim_v31'
down_revision = '013_active_receipt_authority_v28'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('publication_scope_claim_v31',
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('namespace', sa.String(128), nullable=False),
        sa.Column('owner_work_id', sa.String(64), sa.ForeignKey('publication_work_v2.id'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('claim_epoch', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('tenant', 'namespace'),
        sa.CheckConstraint("status IN ('HELD','RELEASED')", name='ck_publication_scope_claim_v31_status'))

def downgrade():
    # Disposable integration database ONLY. Prohibit live production downgrade.
    op.drop_table('publication_scope_claim_v31')

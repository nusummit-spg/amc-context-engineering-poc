"""Add exact active publication receipt authority. Never backfill blindly.

Revision ID: 013_active_receipt_authority_v28
Revises: 012_wave19_durable_pub

The migration is additive: legacy pointer rows do not become serving eligible
until an authorized publication has generated fresh evidence and bound authority.
"""
from alembic import op
import sqlalchemy as sa

revision='013_active_receipt_authority_v28'
down_revision='012_wave19_durable_pub'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('publication_active_authority_v28',
        sa.Column('tenant',sa.String(128),primary_key=True),
        sa.Column('namespace',sa.String(128),primary_key=True),
        sa.Column('generation_id',sa.String(64),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('pointer_epoch',sa.Integer(),nullable=False),
        sa.Column('work_id',sa.String(64),sa.ForeignKey('publication_work_v2.id'),nullable=False),
        sa.Column('receipt_id',sa.String(64),sa.ForeignKey('publication_receipt_v2.id'),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('suspended_by',sa.String(64)),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED')",name='ck_authority_v28_status'))
    op.create_table('publication_authority_preimage_v28',
        sa.Column('work_id',sa.String(64),sa.ForeignKey('publication_work_v2.id'),primary_key=True),
        sa.Column('tenant',sa.String(128),nullable=False),
        sa.Column('namespace',sa.String(128),nullable=False),
        sa.Column('previous_generation',sa.String(64)),
        sa.Column('previous_digest',sa.String(64)),
        sa.Column('previous_work_id',sa.String(64)),
        sa.Column('previous_receipt_id',sa.String(64)),
        sa.Column('captured_at',sa.DateTime(),nullable=False))
    op.create_index('idx_authority_preimage_tenant','publication_authority_preimage_v28',['tenant','namespace'])


def downgrade():
    # Use ONLY in disposable test databases; NEVER downgrade an active release.
    op.drop_index('idx_authority_preimage_tenant',table_name='publication_authority_preimage_v28')
    op.drop_table('publication_authority_preimage_v28')
    op.drop_table('publication_active_authority_v28')

"""Append-only query evidence and pilot feedback (Wave 4.0, TDS-40 E9/E7).

Revision ID: 017_query_evidence_feedback_v40
Revises: 016_fin_structured_plane_v40

Mirrors amc_publication/evidence40.py. On PostgreSQL, UPDATE and DELETE are revoked from PUBLIC on both tables;
deployments must grant only INSERT and SELECT to the application role (the code has no update/delete path).
"""
from alembic import op
import sqlalchemy as sa

revision = '017_query_evidence_feedback_v40'
down_revision = '016_fin_structured_plane_v40'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'query_evidence_v40',
        sa.Column('request_id', sa.String(64), primary_key=True),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('user_id', sa.String(128), nullable=True),
        sa.Column('channel', sa.String(16), nullable=False),
        sa.Column('answer_kind', sa.String(16), nullable=False),
        sa.Column('abstention_code', sa.String(64), nullable=True),
        sa.Column('serving_engine', sa.String(64), nullable=True),
        sa.Column('faiss_generation_id', sa.String(64), nullable=True),
        sa.Column('faiss_receipt_id', sa.String(64), nullable=True),
        sa.Column('fin_dataset_version', sa.String(64), nullable=True),
        sa.Column('fin_receipt_id', sa.String(64), nullable=True),
        sa.Column('structured_result_hash', sa.String(80), nullable=True),
        sa.Column('citations', sa.JSON(), nullable=False),
        sa.Column('provider', sa.String(64), nullable=True),
        sa.Column('model', sa.String(128), nullable=True),
        sa.Column('question_scrubbed', sa.Text(), nullable=False),
        sa.Column('answer_sha256', sa.String(64), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("answer_kind IN ('STRUCTURED','DOCUMENT','MIXED','ABSTAIN','CLARIFY')",
                           name='ck_query_evidence_v40_kind'),
        sa.CheckConstraint("channel IN ('answer','stream')", name='ck_query_evidence_v40_channel'),
    )
    op.create_index('idx_query_evidence_v40_tenant_time', 'query_evidence_v40', ['tenant', 'created_at'])
    op.create_table(
        'pilot_feedback_v40',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('request_id', sa.String(64), sa.ForeignKey('query_evidence_v40.request_id'), nullable=False),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('user_id', sa.String(128), nullable=False),
        sa.Column('rating', sa.String(8), nullable=False),
        sa.Column('reason', sa.String(32), nullable=False),
        sa.Column('comment_scrubbed', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('request_id', 'user_id', name='uq_pilot_feedback_v40_once'),
        sa.CheckConstraint("rating IN ('UP','DOWN')", name='ck_pilot_feedback_v40_rating'),
        sa.CheckConstraint("reason IN ('WRONG_NUMBER','WRONG_CITATION','OUTDATED','INCOMPLETE','NOT_RELEVANT',"
                           "'HELPFUL','OTHER')", name='ck_pilot_feedback_v40_reason'),
    )
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('REVOKE UPDATE, DELETE, TRUNCATE ON query_evidence_v40, pilot_feedback_v40 FROM PUBLIC')


def downgrade():
    # Disposable databases only.
    op.drop_table('pilot_feedback_v40')
    op.drop_index('idx_query_evidence_v40_tenant_time', table_name='query_evidence_v40')
    op.drop_table('query_evidence_v40')

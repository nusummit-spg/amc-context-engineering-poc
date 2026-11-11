"""002: Feedback evaluation tables — response_feedback, unified_evaluation_records, query_evidence

Revision ID: 002_feedback_tables
Revises: 001_base_schema
Create Date: 2026-10-15 00:00:00.000000

Reconstructed baseline migration. See remediation/wave2_2/01_MIGRATION_HISTORY.md.

Tables created:
  - response_feedback       (raw reviewer feedback records)
  - unified_evaluation_records  (adjudicated evaluation output, referenced by repair_proposals)
  - query_evidence          (query context snapshot; has FK to unified_evaluation_records)

NOTE: repair_proposals (created in 003) has a FK to unified_evaluation_records.
      query_evidence has a FK to unified_evaluation_records, so that table must
      be created before query_evidence within this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = '002_feedback_tables'
down_revision = '001_base_schema'
branch_labels = None
depends_on = None

def upgrade() -> None:

    # ------------------------------------------------------------------ #
    # response_feedback
    # Raw reviewer feedback submissions (Step 1 of feedback pipeline).
    # ------------------------------------------------------------------ #
    op.create_table(
        'response_feedback',
        sa.Column('feedback_id', sa.String(64), nullable=False),
        sa.Column('response_id', sa.String(64), nullable=False),
        sa.Column('interaction_id', sa.String(64), nullable=False),
        sa.Column('session_id', sa.String(64), nullable=False),
        sa.Column('turn_number', sa.Integer(), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=True),
        sa.Column('actor_id', sa.String(64), nullable=True),
        sa.Column('actor_role', sa.String(60), nullable=True),
        sa.Column('selected_categories', sa.JSON(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('answer_relevance_score', sa.Integer(), nullable=True),
        sa.Column('source_quality_score', sa.Integer(), nullable=True),
        # Enhanced columns (MISSING_SCHEMA_DEFINITIONS.md "Enhanced Table 2")
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('response_summary', sa.Text(), nullable=True),
        sa.Column('feedback_span', sa.JSON(), nullable=True),
        sa.Column('classification_json', sa.JSON(), nullable=True),
        sa.Column('root_cause', sa.String(30), nullable=True),
        sa.Column('unified_record_ref', sa.String(64), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint('feedback_id', name='pk_response_feedback'),
        sa.UniqueConstraint('feedback_id', name='uq_response_feedback_id'),
    )
    op.create_index('idx_rf_response_id', 'response_feedback', ['response_id'])
    op.create_index('idx_rf_session_id', 'response_feedback', ['session_id'])
    op.create_index('idx_rf_actor_id', 'response_feedback', ['actor_id'])
    op.create_index('idx_rf_actor_role', 'response_feedback', ['actor_role'])

    # ------------------------------------------------------------------ #
    # unified_evaluation_records
    # Adjudicated evaluation output written by the feedback-loop pipeline.
    # Must be created before query_evidence (which FK-references it).
    # Also referenced by repair_proposals in migration 003.
    # ------------------------------------------------------------------ #
    op.create_table(
        'unified_evaluation_records',
        sa.Column('session_id', sa.String(36), nullable=False),
        sa.Column('response_id', sa.String(36), nullable=False),
        sa.Column('entry_route', sa.String(40), nullable=False),
        sa.Column('feedback_ref', sa.String(36),
                  sa.ForeignKey('response_feedback.feedback_id', ondelete='SET NULL'),
                  nullable=True, unique=True),
        sa.Column('evidence_snapshot_ref', sa.String(64), nullable=False),
        sa.Column('root_cause', sa.String(30), nullable=False),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('lifecycle_status', sa.String(20), nullable=False,
                  server_default='open'),
        sa.Column('dissatisfaction_evidence_json', sa.JSON(), nullable=True),
        sa.Column('repair', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('repair_target', sa.String(10), nullable=True),
        sa.Column('deterministic_results', sa.JSON(), nullable=True),
        sa.Column('gnn_plausibility_score', sa.Float(), nullable=True),
        sa.Column('semantic_results', sa.JSON(), nullable=True),
        sa.Column('llm_evaluation', sa.JSON(), nullable=True),
        sa.Column('adjudication_verdict', sa.String(30), nullable=True),
        sa.Column('adjudication_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.Column('created_by', sa.String(60), nullable=True,
                  server_default='feedback_loop_module'),
        sa.PrimaryKeyConstraint('session_id', 'response_id',
                                name='pk_unified_evaluation_records'),
        sa.UniqueConstraint('response_id', name='uq_unified_response_id'),
        sa.CheckConstraint(
            "entry_route IN ('hitl','automatic','dissatisfaction_converted')",
            name='ck_unified_entry_route'),
        sa.CheckConstraint(
            "root_cause IN ('knowledge','retrieval','graph','context_engineering',"
            "'model','guardrail','compliance','presentation','feedback_invalid')",
            name='ck_unified_root_cause'),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low') OR severity IS NULL",
            name='ck_unified_severity'),
        sa.CheckConstraint(
            "lifecycle_status IN ('open','diagnosing','resolved','monitoring')",
            name='ck_unified_lifecycle_status'),
        sa.CheckConstraint(
            "repair_target IN ('vector','graph') OR repair_target IS NULL",
            name='ck_unified_repair_target'),
        sa.CheckConstraint(
            "adjudication_verdict IN ('valid','partially_valid','invalid',"
            "'subjective','insufficient_evidence') OR adjudication_verdict IS NULL",
            name='ck_unified_adjudication_verdict'),
    )
    op.create_index('idx_unified_entry_route', 'unified_evaluation_records', ['entry_route'])
    op.create_index('idx_unified_root_cause', 'unified_evaluation_records', ['root_cause'])
    op.create_index('idx_unified_severity', 'unified_evaluation_records', ['severity'])
    op.create_index('idx_unified_lifecycle', 'unified_evaluation_records', ['lifecycle_status'])
    op.create_index('idx_unified_created_at', 'unified_evaluation_records', ['created_at'])
    op.create_index('idx_unified_evidence_ref', 'unified_evaluation_records', ['evidence_snapshot_ref'])

    # ------------------------------------------------------------------ #
    # query_evidence
    # Query context snapshot; has FK to unified_evaluation_records and
    # chat_sessions (created in 001).
    # ------------------------------------------------------------------ #
    op.create_table(
        'query_evidence',
        sa.Column('response_id', sa.String(64), nullable=False),
        sa.Column('session_id', sa.String(64),
                  sa.ForeignKey('chat_sessions.session_id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('tenant_id', sa.String(36), nullable=True),
        sa.Column('request_id', sa.String(64), nullable=True),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('query_type', sa.String(60), nullable=True),
        sa.Column('query_intent', sa.String(120), nullable=True),
        sa.Column('retrieval_mode', sa.String(40), nullable=False,
                  server_default='contextgraph'),
        sa.Column('serving_engine', sa.String(60), nullable=True),
        sa.Column('assembled_context_json', sa.JSON(), nullable=False),
        sa.Column('synthesis_output_json', sa.JSON(), nullable=False),
        sa.Column('graph_highlight_json', sa.JSON(), nullable=True),
        sa.Column('traditional_result_json', sa.JSON(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('retrieval_latency_ms', sa.Integer(), nullable=True),
        sa.Column('synthesis_latency_ms', sa.Integer(), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('confidence_level', sa.String(10), nullable=True),
        sa.Column('audit_id', sa.String(64),
                  sa.ForeignKey('audit_metadata.audit_id'),
                  nullable=True),
        sa.Column('linked_violations_json', sa.JSON(), nullable=True),
        sa.Column('has_feedback', sa.Boolean(), server_default=sa.false()),
        sa.Column('feedback_summary_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('archived', sa.Boolean(), server_default=sa.false()),
        # Enhanced columns (MISSING_SCHEMA_DEFINITIONS.md "Enhanced Table 3")
        sa.Column('entry_route', sa.String(40), nullable=True),
        sa.Column('root_cause', sa.String(30), nullable=True),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('dissatisfaction_evidence_json', sa.JSON(), nullable=True),
        sa.Column('unified_record_ref', sa.String(64),
                  sa.ForeignKey('unified_evaluation_records.response_id',
                                ondelete='SET NULL'),
                  nullable=True, unique=True),
        sa.PrimaryKeyConstraint('session_id', 'response_id', name='pk_query_evidence'),
        sa.UniqueConstraint('response_id', name='uq_query_evidence_response_id'),
        sa.CheckConstraint(
            "confidence_level IN ('high','medium','low') OR confidence_level IS NULL",
            name='ck_query_confidence_level'),
    )
    op.create_index('idx_qe_session_user', 'query_evidence', ['session_id', 'user_id'])
    op.create_index('idx_qe_user_session', 'query_evidence', ['user_id', 'session_id'])
    op.create_index('idx_qe_tenant_user', 'query_evidence', ['tenant_id', 'user_id'])
    op.create_index('idx_qe_unified_ref', 'query_evidence', ['unified_record_ref'])
    op.create_index('idx_qe_entry_route', 'query_evidence', ['entry_route'])
    op.create_index('idx_qe_root_cause', 'query_evidence', ['root_cause'])
    op.create_index('idx_qe_created_at', 'query_evidence', ['created_at'])

def downgrade() -> None:
    # Drop in reverse creation order (query_evidence depends on unified_evaluation_records)
    op.drop_index('idx_qe_created_at', table_name='query_evidence')
    op.drop_index('idx_qe_root_cause', table_name='query_evidence')
    op.drop_index('idx_qe_entry_route', table_name='query_evidence')
    op.drop_index('idx_qe_unified_ref', table_name='query_evidence')
    op.drop_index('idx_qe_tenant_user', table_name='query_evidence')
    op.drop_index('idx_qe_user_session', table_name='query_evidence')
    op.drop_index('idx_qe_session_user', table_name='query_evidence')
    op.drop_table('query_evidence')

    op.drop_index('idx_unified_evidence_ref', table_name='unified_evaluation_records')
    op.drop_index('idx_unified_created_at', table_name='unified_evaluation_records')
    op.drop_index('idx_unified_lifecycle', table_name='unified_evaluation_records')
    op.drop_index('idx_unified_severity', table_name='unified_evaluation_records')
    op.drop_index('idx_unified_root_cause', table_name='unified_evaluation_records')
    op.drop_index('idx_unified_entry_route', table_name='unified_evaluation_records')
    op.drop_table('unified_evaluation_records')

    op.drop_index('idx_rf_actor_role', table_name='response_feedback')
    op.drop_index('idx_rf_actor_id', table_name='response_feedback')
    op.drop_index('idx_rf_session_id', table_name='response_feedback')
    op.drop_index('idx_rf_response_id', table_name='response_feedback')
    op.drop_table('response_feedback')

"""Align the app schema with the ORM models for the verified PostgreSQL pilot (Wave 3.1, WP02).

Revision ID: 015_app_schema_alignment_v31
Revises: 014_publication_scope_claim_v31

Why: in AMC_VERIFIED_SERVING_MODE=enforce the app never runs create_all, so a database that
was only migrated 001-014 lacked tables and columns the models read and write (found by
comparing the models with a real migrated PostgreSQL database):
  * six model tables had no migration: compliance_rules, feedback_issues,
    feedback_issue_category_counts, fund_schemes, revoked_tokens, violations
    (revoked_tokens backs JWT revocation);
  * chat_sessions lacked ended_at and audit_id, which every chat session insert/select uses;
  * response_feedback lacked 8 columns the query path selects on EVERY request (the
    pending-feedback check failed with UndefinedColumn on a 014-only database).

Scope: additive only. Nothing is dropped or renamed. The compliance ``audit_metadata`` table
still differs from its model (a different feature, denied by the pilot perimeter) and a few
nullability differences remain; they are pinned as known drift in
tests/live31/test_pg_migration31.py. Use downgrade on a disposable database only.
"""
from alembic import op
import sqlalchemy as sa

revision = '015_app_schema_alignment_v31'
down_revision = '014_publication_scope_claim_v31'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('compliance_rules',
    sa.Column('rule_id', sa.String(length=120), nullable=False),
    sa.Column('regulation_id', sa.String(length=120), nullable=True),
    sa.Column('rule_type', sa.String(length=20), nullable=False),
    sa.Column('region', sa.String(length=10), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('condition_plain_text', sa.Text(), nullable=True),
    sa.Column('condition_code_json', sa.JSON(), nullable=True),
    sa.Column('applicable_categories', sa.JSON(), nullable=True),
    sa.Column('exclusions_json', sa.JSON(), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('enforcement_level', sa.String(length=20), nullable=True),
    sa.Column('confidence_threshold', sa.Float(), nullable=True),
    sa.Column('required_evidence_types', sa.JSON(), nullable=True),
    sa.Column('effective_from', sa.String(length=40), nullable=True),
    sa.Column('effective_to', sa.String(length=40), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('regulation_section', sa.String(length=255), nullable=True),
    sa.Column('document_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.Column('updated_at', sa.String(length=40), nullable=False),
    sa.Column('last_modified_by', sa.String(length=120), nullable=True),
    sa.CheckConstraint("region IN ('SEBI','SEC','ESMA')", name='ck_rule_region'),
    sa.CheckConstraint("rule_type IN ('portfolio','governance','kyc','risk','reporting')", name='ck_rule_type'),
    sa.CheckConstraint("severity IN ('critical','high','medium','low')", name='ck_rule_severity'),
    sa.CheckConstraint('confidence_threshold >= 0.0 AND confidence_threshold <= 1.0', name='ck_rule_confidence_threshold'),
    sa.PrimaryKeyConstraint('rule_id'),
    sa.UniqueConstraint('rule_id', 'region', 'version_number', name='uq_rule_region_version')
    )
    op.create_index(op.f('ix_compliance_rules_is_active'), 'compliance_rules', ['is_active'], unique=False)
    op.create_index(op.f('ix_compliance_rules_region'), 'compliance_rules', ['region'], unique=False)
    op.create_index(op.f('ix_compliance_rules_rule_type'), 'compliance_rules', ['rule_type'], unique=False)
    op.create_index(op.f('ix_compliance_rules_severity'), 'compliance_rules', ['severity'], unique=False)
    op.create_table('feedback_issues',
    sa.Column('issue_id', sa.String(length=64), nullable=False),
    sa.Column('canonical_query_text', sa.Text(), nullable=False),
    sa.Column('query_hash', sa.String(length=64), nullable=False),
    sa.Column('query_embedding_ref', sa.String(length=64), nullable=True),
    sa.Column('primary_entities', sa.JSON(), nullable=False),
    sa.Column('taxonomy_paths', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('repair_task_id', sa.String(length=64), nullable=True),
    sa.Column('contributor_count', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.Column('updated_at', sa.String(length=40), nullable=False),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('issue_id')
    )
    op.create_index('idx_feedback_issues_created', 'feedback_issues', ['created_at'], unique=False)
    op.create_index('idx_feedback_issues_query_hash', 'feedback_issues', ['query_hash'], unique=False)
    op.create_index('idx_feedback_issues_status', 'feedback_issues', ['status'], unique=False)
    op.create_index('idx_feedback_issues_tenant', 'feedback_issues', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_feedback_issues_created_at'), 'feedback_issues', ['created_at'], unique=False)
    op.create_index(op.f('ix_feedback_issues_query_hash'), 'feedback_issues', ['query_hash'], unique=False)
    op.create_index(op.f('ix_feedback_issues_status'), 'feedback_issues', ['status'], unique=False)
    op.create_index(op.f('ix_feedback_issues_tenant_id'), 'feedback_issues', ['tenant_id'], unique=False)
    op.create_table('fund_schemes',
    sa.Column('fund_id', sa.String(length=64), nullable=False),
    sa.Column('isin', sa.String(length=20), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('fund_house', sa.String(length=255), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('mandate', sa.Text(), nullable=True),
    sa.Column('risk_profile', sa.String(length=40), nullable=True),
    sa.Column('aum_crores', sa.Float(), nullable=True),
    sa.Column('nav_per_unit', sa.Float(), nullable=True),
    sa.Column('region', sa.String(length=10), nullable=False),
    sa.Column('applicable_rules_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.Column('updated_at', sa.String(length=40), nullable=False),
    sa.CheckConstraint("region IN ('SEBI','SEC','ESMA')", name='ck_fund_region'),
    sa.PrimaryKeyConstraint('fund_id'),
    sa.UniqueConstraint('fund_id', 'region', name='uq_fund_region'),
    sa.UniqueConstraint('isin')
    )
    op.create_index(op.f('ix_fund_schemes_category'), 'fund_schemes', ['category'], unique=False)
    op.create_index(op.f('ix_fund_schemes_fund_house'), 'fund_schemes', ['fund_house'], unique=False)
    op.create_index(op.f('ix_fund_schemes_region'), 'fund_schemes', ['region'], unique=False)
    op.create_table('revoked_tokens',
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('username', sa.String(length=128), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('reason', sa.String(length=255), nullable=False),
    sa.Column('revoked_by_ip', sa.String(length=45), nullable=True),
    sa.PrimaryKeyConstraint('jti')
    )
    op.create_index('idx_revoked_tokens_expires', 'revoked_tokens', ['expires_at'], unique=False)
    op.create_index('idx_revoked_tokens_username_revoked', 'revoked_tokens', ['username', 'revoked_at'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_expires_at'), 'revoked_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_jti'), 'revoked_tokens', ['jti'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_revoked_at'), 'revoked_tokens', ['revoked_at'], unique=False)
    op.create_index(op.f('ix_revoked_tokens_username'), 'revoked_tokens', ['username'], unique=False)
    op.create_table('feedback_issue_category_counts',
    sa.Column('issue_id', sa.String(length=64), nullable=False),
    sa.Column('category_code', sa.String(length=10), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.String(length=40), nullable=False),
    sa.ForeignKeyConstraint(['issue_id'], ['feedback_issues.issue_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('issue_id', 'category_code')
    )
    op.create_index('idx_category_counts_issue_id', 'feedback_issue_category_counts', ['issue_id'], unique=False)
    op.create_table('violations',
    sa.Column('violation_id', sa.String(length=64), nullable=False),
    sa.Column('audit_id', sa.String(length=64), nullable=False),
    sa.Column('rule_id', sa.String(length=120), nullable=False),
    sa.Column('fund_id', sa.String(length=64), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('violation_type', sa.String(length=20), nullable=False),
    sa.Column('region', sa.String(length=10), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('actual_value', sa.String(length=120), nullable=True),
    sa.Column('threshold_value', sa.String(length=120), nullable=True),
    sa.Column('gap_percentage', sa.Float(), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=False),
    sa.Column('evidence_count', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('detected_at', sa.String(length=40), nullable=False),
    sa.Column('reviewed_at', sa.String(length=40), nullable=True),
    sa.Column('resolved_at', sa.String(length=40), nullable=True),
    sa.Column('resolution_action', sa.String(length=120), nullable=True),
    sa.Column('resolved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.Column('evidence_docs_json', sa.JSON(), nullable=True),
    sa.Column('audit_trail_json', sa.JSON(), nullable=True),
    sa.Column('escalation_level', sa.Integer(), nullable=True),
    sa.Column('escalation_triggered_at', sa.String(length=40), nullable=True),
    sa.Column('escalation_path_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.Column('updated_at', sa.String(length=40), nullable=False),
    sa.Column('created_by', sa.String(length=120), nullable=True),
    sa.CheckConstraint("region IN ('SEBI','SEC','ESMA')", name='ck_violation_region'),
    sa.CheckConstraint("severity IN ('critical','high','medium','low')", name='ck_violation_severity'),
    sa.CheckConstraint("status IN ('detected','reviewed','remediated','closed','waived')", name='ck_violation_status'),
    sa.CheckConstraint("violation_type IN ('portfolio','governance','kyc','risk','reporting')", name='ck_violation_type'),
    sa.CheckConstraint('confidence_score >= 0.0 AND confidence_score <= 1.0', name='ck_violation_confidence'),
    sa.ForeignKeyConstraint(['audit_id'], ['audit_metadata.audit_id'], ),
    sa.PrimaryKeyConstraint('violation_id'),
    sa.UniqueConstraint('audit_id', 'rule_id', 'fund_id', name='uq_violation_audit_rule_fund')
    )
    op.create_index('idx_violation_fund_status', 'violations', ['fund_id', 'status'], unique=False)
    op.create_index('idx_violation_region_severity', 'violations', ['region', 'severity'], unique=False)
    op.create_index(op.f('ix_violations_audit_id'), 'violations', ['audit_id'], unique=False)
    op.create_index(op.f('ix_violations_created_at'), 'violations', ['created_at'], unique=False)
    op.create_index(op.f('ix_violations_detected_at'), 'violations', ['detected_at'], unique=False)
    op.create_index(op.f('ix_violations_escalation_level'), 'violations', ['escalation_level'], unique=False)
    op.create_index(op.f('ix_violations_fund_id'), 'violations', ['fund_id'], unique=False)
    op.create_index(op.f('ix_violations_region'), 'violations', ['region'], unique=False)
    op.create_index(op.f('ix_violations_rule_id'), 'violations', ['rule_id'], unique=False)
    op.create_index(op.f('ix_violations_severity'), 'violations', ['severity'], unique=False)
    op.create_index(op.f('ix_violations_status'), 'violations', ['status'], unique=False)
    # chat_sessions: columns the ORM reads and writes (SQLite needs batch mode for the FK).
    with op.batch_alter_table('chat_sessions') as batch:
        batch.add_column(sa.Column('ended_at', sa.String(length=40), nullable=True))
        batch.add_column(sa.Column('audit_id', sa.String(length=64), nullable=True))
        batch.create_index('ix_chat_sessions_audit_id', ['audit_id'], unique=False)
        batch.create_foreign_key('fk_chat_sessions_audit_id', 'audit_metadata', ['audit_id'], ['audit_id'])
    # The model declares updated_at NOT NULL; fill any gaps first so the change cannot fail.
    op.execute("UPDATE chat_sessions SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table('chat_sessions') as batch:
        batch.alter_column('updated_at', existing_type=sa.String(length=40), nullable=False)

    # response_feedback: the query path runs a pending-feedback check on EVERY request and selects
    # these columns; on a database migrated only to 014 it failed with UndefinedColumn each time.
    with op.batch_alter_table('response_feedback') as batch:
        batch.add_column(sa.Column('completeness_score', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('automated_category', sa.String(length=60), nullable=True))
        batch.add_column(sa.Column('automated_confidence', sa.Float(), nullable=True))
        batch.add_column(sa.Column('client_timestamp', sa.String(length=40), nullable=True))
        batch.add_column(sa.Column('audit_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('violation_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('issue_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('match_type', sa.String(length=20), nullable=True))
        batch.create_index('ix_response_feedback_audit_id', ['audit_id'], unique=False)
        batch.create_index('ix_response_feedback_issue_id', ['issue_id'], unique=False)
        batch.create_foreign_key('fk_response_feedback_issue_id', 'feedback_issues', ['issue_id'], ['issue_id'],
                                 ondelete='SET NULL')
        batch.create_foreign_key('fk_response_feedback_audit_id', 'audit_metadata', ['audit_id'], ['audit_id'])
        batch.create_foreign_key('fk_response_feedback_violation_id', 'violations', ['violation_id'], ['violation_id'])
        batch.create_check_constraint('ck_feedback_relevance_score',
                                      'answer_relevance_score IS NULL OR (answer_relevance_score BETWEEN 1 AND 5)')
        batch.create_check_constraint('ck_feedback_source_score',
                                      'source_quality_score IS NULL OR (source_quality_score BETWEEN 1 AND 5)')
        batch.create_check_constraint('ck_feedback_completeness_score',
                                      'completeness_score IS NULL OR (completeness_score BETWEEN 1 AND 5)')
        batch.create_check_constraint('ck_feedback_automated_confidence',
                                      'automated_confidence IS NULL OR (automated_confidence BETWEEN 0.0 AND 1.0)')
    op.execute("UPDATE response_feedback SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table('response_feedback') as batch:
        batch.alter_column('updated_at', existing_type=sa.String(length=40), nullable=False)


def downgrade():
    # Disposable test databases ONLY; never downgrade a database that serves a release.
    with op.batch_alter_table('response_feedback') as batch:
        batch.alter_column('updated_at', existing_type=sa.String(length=40), nullable=True)
        batch.drop_constraint('ck_feedback_automated_confidence', type_='check')
        batch.drop_constraint('ck_feedback_completeness_score', type_='check')
        batch.drop_constraint('ck_feedback_source_score', type_='check')
        batch.drop_constraint('ck_feedback_relevance_score', type_='check')
        batch.drop_constraint('fk_response_feedback_violation_id', type_='foreignkey')
        batch.drop_constraint('fk_response_feedback_audit_id', type_='foreignkey')
        batch.drop_constraint('fk_response_feedback_issue_id', type_='foreignkey')
        batch.drop_index('ix_response_feedback_issue_id')
        batch.drop_index('ix_response_feedback_audit_id')
        for col in ('match_type', 'issue_id', 'violation_id', 'audit_id', 'client_timestamp',
                    'automated_confidence', 'automated_category', 'completeness_score'):
            batch.drop_column(col)
    with op.batch_alter_table('chat_sessions') as batch:
        batch.alter_column('updated_at', existing_type=sa.String(length=40), nullable=True)
        batch.drop_constraint('fk_chat_sessions_audit_id', type_='foreignkey')
        batch.drop_index('ix_chat_sessions_audit_id')
        batch.drop_column('audit_id')
        batch.drop_column('ended_at')
    op.drop_table('violations')
    op.drop_table('feedback_issue_category_counts')
    op.drop_table('revoked_tokens')
    op.drop_table('fund_schemes')
    op.drop_table('feedback_issues')
    op.drop_table('compliance_rules')

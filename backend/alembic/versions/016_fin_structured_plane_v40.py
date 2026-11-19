"""Verified structured data plane ("fin") tables (Wave 4.0, TDS-40 E1/E2).

Revision ID: 016_fin_structured_plane_v40
Revises: 015_app_schema_alignment_v31

Additive only. Mirrors amc_publication/fin40.py exactly (tests/live40 compares the migrated schema with the
models). Values are scaled integers (micro-units) so sums are exact on every engine. Activation of a dataset
version is a single SQL transaction in fin40.activate_dataset; nothing here activates anything.
"""
from alembic import op
import sqlalchemy as sa

revision = '016_fin_structured_plane_v40'
down_revision = '015_app_schema_alignment_v31'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fin_dataset_version_v40',
        sa.Column('dataset_version', sa.String(64), primary_key=True),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('domain', sa.String(64), nullable=False),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('expected_rows', sa.Integer(), nullable=False),
        sa.Column('parsed_rows', sa.Integer(), nullable=False),
        sa.Column('valid_rows', sa.Integer(), nullable=False),
        sa.Column('rejected_rows', sa.Integer(), nullable=False),
        sa.Column('metric_registry_version', sa.String(64), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('manifest_sha256', sa.String(64), nullable=False),
        sa.Column('signature', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('STAGED','ACTIVE','RETIRED','QUARANTINED')", name='ck_fin_dataset_v40_status'),
    )
    op.create_index('idx_fin_dataset_v40_tenant', 'fin_dataset_version_v40', ['tenant', 'domain', 'status'])

    op.create_table(
        'fin_source_row_v40',
        sa.Column('source_row_id', sa.String(64), primary_key=True),
        sa.Column('dataset_version', sa.String(64), sa.ForeignKey('fin_dataset_version_v40.dataset_version'),
                  nullable=False),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('physical_row_number', sa.Integer(), nullable=False),
        sa.Column('source_file', sa.String(256), nullable=False),
        sa.Column('raw_row_sha256', sa.String(64), nullable=False),
        sa.Column('raw', sa.JSON(), nullable=False),
        sa.Column('validation_status', sa.String(16), nullable=False),
        sa.Column('rejection_reason', sa.String(64), nullable=True),
        sa.UniqueConstraint('dataset_version', 'physical_row_number', name='uq_fin_source_row_v40_pos'),
        sa.CheckConstraint("validation_status IN ('VALID','REJECTED')", name='ck_fin_source_row_v40_status'),
    )

    op.create_table(
        'fin_plan_option_v40',
        sa.Column('dataset_version', sa.String(64), sa.ForeignKey('fin_dataset_version_v40.dataset_version'),
                  primary_key=True),
        sa.Column('plan_option_id', sa.String(64), primary_key=True),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('source_row_id', sa.String(64), sa.ForeignKey('fin_source_row_v40.source_row_id'), nullable=False),
        sa.Column('scheme_code', sa.String(32), nullable=False),
        sa.Column('amc_id', sa.String(128), nullable=False),
        sa.Column('amc_name', sa.String(256), nullable=False),
        sa.Column('scheme_id', sa.String(256), nullable=False),
        sa.Column('scheme_name', sa.String(512), nullable=False),
        sa.Column('scheme_type', sa.String(128), nullable=True),
        sa.Column('scheme_category', sa.String(256), nullable=True),
        sa.Column('plan_option_name', sa.String(512), nullable=False),
        sa.Column('plan', sa.String(16), nullable=False),
        sa.Column('option', sa.String(16), nullable=False),
        sa.Column('isins', sa.JSON(), nullable=False),
        sa.Column('launch_date', sa.Date(), nullable=True),
    )
    op.create_index('idx_fin_po_v40_amc', 'fin_plan_option_v40', ['dataset_version', 'amc_id'])
    op.create_index('idx_fin_po_v40_code', 'fin_plan_option_v40', ['dataset_version', 'scheme_code'])

    op.create_table(
        'fin_nav_observation_v40',
        sa.Column('observation_id', sa.String(64), primary_key=True),
        sa.Column('dataset_version', sa.String(64), sa.ForeignKey('fin_dataset_version_v40.dataset_version'),
                  nullable=False),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('plan_option_id', sa.String(64), nullable=False),
        sa.Column('source_row_id', sa.String(64), nullable=False),
        sa.Column('nav_micro', sa.BigInteger(), nullable=False),
        sa.Column('nav_date', sa.Date(), nullable=False),
    )
    op.create_index('idx_fin_nav_v40_po', 'fin_nav_observation_v40', ['dataset_version', 'plan_option_id'])

    op.create_table(
        'fin_aaum_observation_v40',
        sa.Column('observation_id', sa.String(64), primary_key=True),
        sa.Column('dataset_version', sa.String(64), sa.ForeignKey('fin_dataset_version_v40.dataset_version'),
                  nullable=False),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('plan_option_id', sa.String(64), nullable=False),
        sa.Column('scheme_id', sa.String(256), nullable=False),
        sa.Column('amc_id', sa.String(128), nullable=False),
        sa.Column('source_row_id', sa.String(64), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('period_label', sa.String(64), nullable=False),
        sa.Column('aaum_micro_cr', sa.BigInteger(), nullable=False),
        sa.Column('grain', sa.String(16), nullable=False),
        sa.Column('valid_for_aggregation', sa.Boolean(), nullable=False),
        sa.CheckConstraint("grain IN ('PLAN_OPTION')", name='ck_fin_aaum_v40_grain'),
    )
    op.create_index('idx_fin_aaum_v40_period', 'fin_aaum_observation_v40',
                    ['dataset_version', 'period_start', 'amc_id'])

    op.create_table(
        'fin_publication_receipt_v40',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('work_id', sa.String(64), sa.ForeignKey('publication_work_v2.id'), nullable=False, unique=True),
        sa.Column('tenant', sa.String(128), nullable=False),
        sa.Column('domain', sa.String(64), nullable=False),
        sa.Column('dataset_version', sa.String(64), nullable=False),
        sa.Column('previous_dataset_version', sa.String(64), nullable=True),
        sa.Column('manifest_sha256', sa.String(64), nullable=False),
        sa.Column('signature_key_id', sa.String(64), nullable=False),
        sa.Column('approval_sha256', sa.String(64), nullable=False),
        sa.Column('proposer', sa.String(64), nullable=False),
        sa.Column('reviewer', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'fin_active_dataset_v40',
        sa.Column('tenant', sa.String(128), primary_key=True),
        sa.Column('domain', sa.String(64), primary_key=True),
        sa.Column('dataset_version', sa.String(64), sa.ForeignKey('fin_dataset_version_v40.dataset_version'),
                  nullable=False),
        sa.Column('receipt_id', sa.String(64), sa.ForeignKey('fin_publication_receipt_v40.id'), nullable=False),
        sa.Column('epoch', sa.Integer(), nullable=False),
        sa.Column('activated_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    # Disposable databases only (TDS-31: schema downgrade is never a rollback strategy).
    for name in ('fin_active_dataset_v40', 'fin_publication_receipt_v40', 'fin_aaum_observation_v40',
                 'fin_nav_observation_v40', 'fin_plan_option_v40', 'fin_source_row_v40', 'fin_dataset_version_v40'):
        op.drop_table(name)

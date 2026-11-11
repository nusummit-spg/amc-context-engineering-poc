"""001: Baseline schema — auth_users, chat_sessions, audit_metadata

Revision ID: 001_base_schema
Revises: None
Create Date: 2026-10-01 00:00:00.000000

Reconstructed baseline migration. The original 001-003 scripts were present
in internal history before open-source publication; recreated from ORM
definitions at Wave 2.2 HEAD after maintainer review.
See remediation/wave2_2/01_MIGRATION_HISTORY.md for decision record.

Tables created: chat_sessions, audit_metadata, auth_users.
"""
from alembic import op
import sqlalchemy as sa

revision = '001_base_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'chat_sessions',
        sa.Column('session_id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
    )
    op.create_index('idx_chat_user', 'chat_sessions', ['user_id'])
    op.create_index('idx_chat_tenant', 'chat_sessions', ['tenant_id'])

    op.create_table(
        'audit_metadata',
        sa.Column('audit_id', sa.String(64), primary_key=True),
        sa.Column('actor_id', sa.String(64), nullable=True),
        sa.Column('action', sa.String(128), nullable=True),
        sa.Column('resource', sa.String(256), nullable=True),
        sa.Column('outcome', sa.String(20), nullable=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('tenant_id', sa.String(64), nullable=True),
    )
    op.create_index('idx_audit_created', 'audit_metadata', ['created_at'])
    op.create_index('idx_audit_actor', 'audit_metadata', ['actor_id'])
    op.create_index('idx_audit_tenant', 'audit_metadata', ['tenant_id'])

    op.create_table(
        'auth_users',
        sa.Column('username', sa.String(128), primary_key=True),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('display_name', sa.String(256), nullable=False),
        sa.Column('email', sa.String(256), nullable=False),
        sa.Column('role', sa.String(128), nullable=False),
        sa.Column('department', sa.String(256), nullable=False, server_default=''),
        sa.Column('avatar_initials', sa.String(10), nullable=False, server_default=''),
        sa.Column('status', sa.String(20), nullable=False, server_default='Active'),
        sa.Column('tenant_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('last_login_ip', sa.String(45), nullable=True),
    )
    op.create_index('idx_auth_email', 'auth_users', ['email'])
    op.create_index('idx_auth_role', 'auth_users', ['role'])
    op.create_index('idx_auth_tenant', 'auth_users', ['tenant_id'])
    op.create_index('idx_auth_status', 'auth_users', ['status'])
    op.create_index('idx_auth_created', 'auth_users', ['created_at'])

def downgrade() -> None:
    op.drop_index('idx_auth_created', table_name='auth_users')
    op.drop_index('idx_auth_status', table_name='auth_users')
    op.drop_index('idx_auth_tenant', table_name='auth_users')
    op.drop_index('idx_auth_role', table_name='auth_users')
    op.drop_index('idx_auth_email', table_name='auth_users')
    op.drop_table('auth_users')
    op.drop_index('idx_audit_tenant', table_name='audit_metadata')
    op.drop_index('idx_audit_actor', table_name='audit_metadata')
    op.drop_index('idx_audit_created', table_name='audit_metadata')
    op.drop_table('audit_metadata')
    op.drop_index('idx_chat_tenant', table_name='chat_sessions')
    op.drop_index('idx_chat_user', table_name='chat_sessions')
    op.drop_table('chat_sessions')

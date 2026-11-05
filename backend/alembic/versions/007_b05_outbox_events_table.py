"""B05: Create outbox_events table for saga pattern

Revision ID: 007_b05_outbox_events
Revises: 006_b04_reindex_jobs
Create Date: 2026-11-05 11:30:00.000000

Wave 1.3 Batch B (B05): Transaction Saga Implementation
- Creates outbox_events table for transactional outbox pattern
- Enables atomic operations across PostgreSQL, Neo4j, and FAISS
- Provides retry mechanism with exponential backoff
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_b05_outbox_events'
down_revision = '006_b04_reindex_jobs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create outbox_events table."""
    
    op.create_table(
        'outbox_events',
        sa.Column('event_id', sa.String(length=64), nullable=False, comment='B05: Unique event identifier'),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False, comment='Type of entity (e.g., repair_proposal)'),
        sa.Column('aggregate_id', sa.String(length=64), nullable=False, comment='ID of the entity'),
        sa.Column('event_type', sa.String(length=64), nullable=False, comment='Event type (e.g., GRAPH_MUTATION_REQUIRED)'),
        sa.Column('payload', sa.JSON(), nullable=False, comment='Full event data'),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending', comment='Event status: pending/processing/completed/failed'),
        sa.Column('created_at', sa.String(length=40), nullable=False, comment='ISO timestamp when event created'),
        sa.Column('processed_at', sa.String(length=40), nullable=True, comment='ISO timestamp when event processed'),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0, comment='Number of retry attempts'),
        sa.Column('max_retries', sa.Integer(), nullable=False, default=3, comment='Maximum retry attempts'),
        sa.Column('error', sa.Text(), nullable=True, comment='Error message if event failed'),
        sa.PrimaryKeyConstraint('event_id'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name='ck_outbox_status')
    )
    
    # Create indexes for efficient processing
    op.create_index('idx_outbox_aggregate_id', 'outbox_events', ['aggregate_id'])
    op.create_index('idx_outbox_status_created', 'outbox_events', ['status', 'created_at'])
    op.create_index('idx_outbox_created_at', 'outbox_events', ['created_at'])


def downgrade() -> None:
    """Drop outbox_events table."""
    
    op.drop_index('idx_outbox_created_at', table_name='outbox_events')
    op.drop_index('idx_outbox_status_created', table_name='outbox_events')
    op.drop_index('idx_outbox_aggregate_id', table_name='outbox_events')
    op.drop_table('outbox_events')

"""B06: Add rolled_back status to repair_proposals

Revision ID: 008_b06_rollback_status
Revises: 007_b05_outbox_events
Create Date: 2026-11-05 12:00:00.000000

Wave 1.3 Batch B (B06): Rollback Mechanism
- Adds 'rolled_back' status to repair_proposals check constraint
- Enables tracking of rolled-back proposals in status field
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '008_b06_rollback_status'
down_revision = '007_b05_outbox_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add rolled_back status to repair_proposals status constraint."""
    
    # Drop old constraint
    op.drop_constraint('ck_proposal_status', 'repair_proposals', type_='check')
    
    # Create new constraint with rolled_back
    op.create_check_constraint(
        'ck_proposal_status',
        'repair_proposals',
        "status IN ('pending', 'approved', 'rejected', 'applied', 'rolled_back')"
    )


def downgrade() -> None:
    """Remove rolled_back status from constraint."""
    
    # Drop new constraint
    op.drop_constraint('ck_proposal_status', 'repair_proposals', type_='check')
    
    # Restore old constraint
    op.create_check_constraint(
        'ck_proposal_status',
        'repair_proposals',
        "status IN ('pending', 'approved', 'rejected', 'applied')"
    )

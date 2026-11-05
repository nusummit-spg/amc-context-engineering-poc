"""B03: Add corrected_value to repair_proposals

Revision ID: 005_b03_corrected_value
Revises: 004_b03_verification
Create Date: 2026-11-05 10:15:00.000000

Wave 1.3 Batch B (B03): Enable Graph Verification
- Adds corrected_value column to repair_proposals table
- This field stores the expected value after mutation
- Used by promotion_service to verify exact value match (C-11)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_b03_corrected_value'
down_revision = '004_b03_verification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add corrected_value column to repair_proposals table."""
    
    op.add_column('repair_proposals',
        sa.Column('corrected_value', sa.Text(), nullable=True,
                  comment='B03: Expected value after graph mutation (for verification)'))


def downgrade() -> None:
    """Remove corrected_value column."""
    
    op.drop_column('repair_proposals', 'corrected_value')

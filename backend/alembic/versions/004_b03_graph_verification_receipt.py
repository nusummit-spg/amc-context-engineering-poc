"""B03: Add verification receipt fields to graph_mutations

Revision ID: 004_b03_verification
Revises: 003_invitation_token_hash
Create Date: 2026-11-05 10:00:00.000000

Wave 1.3 Batch B (B03): Graph Verification Enhancement
- Adds verified_value column (actual value read back from graph)
- Adds verification_timestamp column (when verification occurred)
- Adds verification_receipt column (full immutable receipt JSON)

These fields provide cryptographic-grade proof that graph mutations
wrote the exact expected values, closing C-11 integrity gate.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_b03_verification'
down_revision = '003_invitation_token_hash'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add B03 verification receipt fields to graph_mutations table."""
    
    # Add verified_value column (TEXT to handle any data type as string)
    op.add_column('graph_mutations', 
        sa.Column('verified_value', sa.Text(), nullable=True,
                  comment='B03: Actual value read back from graph after mutation'))
    
    # Add verification_timestamp column
    op.add_column('graph_mutations',
        sa.Column('verification_timestamp', sa.String(length=40), nullable=True,
                  comment='B03: ISO timestamp when verification occurred'))
    
    # Add verification_receipt column (JSON with full proof)
    op.add_column('graph_mutations',
        sa.Column('verification_receipt', sa.JSON(), nullable=True,
                  comment='B03: Immutable receipt with entity_id, attribute, expected/verified values'))


def downgrade() -> None:
    """Remove B03 verification receipt fields."""
    
    op.drop_column('graph_mutations', 'verification_receipt')
    op.drop_column('graph_mutations', 'verification_timestamp')
    op.drop_column('graph_mutations', 'verified_value')

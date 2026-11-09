"""Wave 1.9 opt-in durable publication engine tables.

Revision ID: 012_wave19_durable_pub
Revises: 011_b08_active_versions

This additive migration does not alter the existing 009/010/011 schemas. Once
v2 has passed dual-system testing, a separate migration can reconcile legacy
schema and retire the obsolete writer. Do not run downgrade on live data.
"""
from alembic import op
import sqlalchemy as sa

revision = "012_wave19_durable_pub"
down_revision = "011_b08_active_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publication_work_v2",
        sa.Column("id",sa.String(64),primary_key=True),
        sa.Column("tenant",sa.String(128),nullable=False),
        sa.Column("idempotency_key",sa.String(128),nullable=False),
        sa.Column("proposal_id",sa.String(128),nullable=False),
        sa.Column("approved_revision",sa.Integer(),nullable=False),
        sa.Column("payload_hash",sa.String(64),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("status",sa.String(20),nullable=False,server_default="queued"),
        sa.Column("epoch",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("fence",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("owner",sa.String(128)),
        sa.Column("lease_until",sa.DateTime()),
        sa.Column("attempts",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("max_attempts",sa.Integer(),nullable=False,server_default="5"),
        sa.Column("last_error",sa.Text()),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("tenant","idempotency_key",name="uq_pub_v2_tenant_key"),
        sa.CheckConstraint("status IN ('queued','leased','published','failed','rollback_pending','rolled_back')",name="ck_pub_v2_status"),
    )
    op.create_index("idx_pub_v2_status_lease","publication_work_v2",["status","lease_until"])
    op.create_table(
        "publication_effect_v2",
        sa.Column("id",sa.String(64),primary_key=True),
        sa.Column("work_id",sa.String(64),sa.ForeignKey("publication_work_v2.id"),nullable=False),
        sa.Column("tenant",sa.String(128),nullable=False),
        sa.Column("kind",sa.String(32),nullable=False),
        sa.Column("target",sa.String(256),nullable=False),
        sa.Column("preimage",sa.JSON(),nullable=False),
        sa.Column("postimage",sa.JSON(),nullable=False),
        sa.Column("pre_hash",sa.String(64),nullable=False),
        sa.Column("post_hash",sa.String(64),nullable=False),
        sa.Column("state",sa.String(20),nullable=False,server_default="prepared"),
        sa.Column("claim_epoch",sa.Integer(),nullable=False),
        sa.Column("verified_at",sa.DateTime()),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("work_id","kind","target",name="uq_pub_v2_effect"),
        sa.CheckConstraint("state IN ('prepared','verified','compensated')",name="ck_pub_v2_effect_state"),
    )
    op.create_table(
        "publication_pointer_v2",
        sa.Column("tenant",sa.String(128),primary_key=True),
        sa.Column("namespace",sa.String(128),primary_key=True),
        sa.Column("generation_id",sa.String(64),nullable=False),
        sa.Column("artifact_digest",sa.String(64),nullable=False),
        sa.Column("epoch",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("activated_at",sa.DateTime(),nullable=False),
    )
    op.create_table(
        "publication_receipt_v2",
        sa.Column("id",sa.String(64),primary_key=True),
        sa.Column("work_id",sa.String(64),sa.ForeignKey("publication_work_v2.id"),nullable=False,unique=True),
        sa.Column("tenant",sa.String(128),nullable=False),
        sa.Column("graph_hash",sa.String(64),nullable=False),
        sa.Column("generation_id",sa.String(64),nullable=False),
        sa.Column("generation_digest",sa.String(64),nullable=False),
        sa.Column("verified",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("created_at",sa.DateTime(),nullable=False),
    )
    op.create_table(
        "feedback_publication_link_v2",
        sa.Column("tenant",sa.String(128),primary_key=True),
        sa.Column("issue_id",sa.String(128),primary_key=True),
        sa.Column("work_id",sa.String(64),sa.ForeignKey("publication_work_v2.id"),nullable=False),
        sa.Column("receipt_id",sa.String(64),sa.ForeignKey("publication_receipt_v2.id"),nullable=False),
        sa.Column("status",sa.String(20),nullable=False,server_default="resolved"),
        sa.Column("updated_at",sa.DateTime(),nullable=False),
    )
    op.create_table(
        "publication_fence_v2",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("counter",sa.Integer(),nullable=False,server_default="0"),
    )
    op.execute("INSERT INTO publication_fence_v2 (id, counter) VALUES (1, 0)")


def downgrade():
    op.drop_table("publication_fence_v2")
    op.drop_table("feedback_publication_link_v2")
    op.drop_table("publication_receipt_v2")
    op.drop_table("publication_pointer_v2")
    op.drop_table("publication_effect_v2")
    op.drop_index("idx_pub_v2_status_lease",table_name="publication_work_v2")
    op.drop_table("publication_work_v2")

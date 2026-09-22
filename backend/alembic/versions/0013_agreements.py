"""agreements: a committed introduction becomes a record, and where both parties are local, a stake

Revision ID: 0013_agreements
Revises: 0012_introductions
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_agreements"
down_revision = "0012_introductions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vm_agreements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("introduction_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("terms", sa.Text(), nullable=False),
        sa.Column("offer", sa.Text(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("recorded_by", sa.String(length=400), nullable=False),
        sa.Column("counterpart_node", sa.String(length=100), nullable=True),
        sa.Column("counterpart_contact", sa.String(length=300), nullable=True),
        sa.Column("document", sa.JSON(), nullable=True),
        sa.Column("linked_type", sa.String(length=30), nullable=True),
        sa.Column("linked_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("bw_projects.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
    )
    op.create_index("ix_vm_agreements_correlation_id", "vm_agreements", ["correlation_id"])


def downgrade():
    op.drop_index("ix_vm_agreements_correlation_id", table_name="vm_agreements")
    op.drop_table("vm_agreements")

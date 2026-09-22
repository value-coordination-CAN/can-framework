"""introductions: consent-based requests travelling a path

Revision ID: 0012_introductions
Revises: 0011_peering_and_query_log
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_introductions"
down_revision = "0011_peering_and_query_log"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vm_introductions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("commitment", sa.String(length=64), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column("hop_index", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(length=400), nullable=True),
        sa.Column("from_node", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by", sa.String(length=400), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("reply_contact", sa.String(length=300), nullable=True),
        sa.Column("reply_slice", sa.JSON(), nullable=True),
        sa.Column("candidate_items", sa.JSON(), nullable=True),
        sa.Column("offer", sa.Text(), nullable=False, server_default=""),
        sa.Column("blocked_by", sa.String(length=100), nullable=True),
        sa.Column("commit_status", sa.String(length=20), nullable=False, server_default="offered"),
        sa.Column("requester_contact", sa.String(length=300), nullable=True),
        sa.Column("routes", sa.JSON(), nullable=True),
    )
    op.create_index("ix_vm_introductions_correlation_id", "vm_introductions", ["correlation_id"])


    # Connection value on peers: carrying builds weight, not carrying is only a missed chance
    op.add_column("vm_peers", sa.Column("carried_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("vm_peers", sa.Column("connections_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("vm_peers", sa.Column("missed_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("vm_peers", "missed_count")
    op.drop_column("vm_peers", "connections_count")
    op.drop_column("vm_peers", "carried_count")
    op.drop_index("ix_vm_introductions_correlation_id", table_name="vm_introductions")
    op.drop_table("vm_introductions")

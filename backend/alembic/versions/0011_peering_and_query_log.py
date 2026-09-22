"""peering between nodes, and a local log of what was asked

Revision ID: 0011_peering_and_query_log
Revises: 0010_value_map_items
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_peering_and_query_log"
down_revision = "0010_value_map_items"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vm_peers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=300), nullable=True),
        sa.Column("public_key", sa.String(length=100), nullable=False),
        sa.Column("trust_weight", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_queries_per_hour", sa.Integer(), nullable=True),
        sa.Column("added_by", sa.String(length=400), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_vm_peers_node_id", "vm_peers", ["node_id"], unique=True)

    op.create_table(
        "vm_query_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("peer_node_id", sa.String(length=100), nullable=True),
        sa.Column("asked_by", sa.String(length=400), nullable=True),
        sa.Column("commitment", sa.String(length=64), nullable=False),
        sa.Column("ttl", sa.Integer(), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column("matched", sa.String(length=10), nullable=False),
        sa.Column("results", sa.Integer(), nullable=False),
    )
    op.create_index("ix_vm_query_log_commitment", "vm_query_log", ["commitment"])


def downgrade():
    op.drop_table("vm_query_log")
    op.drop_index("ix_vm_peers_node_id", table_name="vm_peers")
    op.drop_table("vm_peers")

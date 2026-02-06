"""linkedin network edges

Revision ID: 016f621224c7
Revises:
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa

revision = "016f621224c7"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "network_edges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_user_id", sa.String(), nullable=False),
        sa.Column("target_user_id", sa.String(), nullable=True),
        sa.Column("target_external_id", sa.String(), nullable=True),
        sa.Column("edge_type", sa.String(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("evidence_ref", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_network_edges_source_user_id", "network_edges", ["source_user_id"])
    op.create_index("ix_network_edges_target_user_id", "network_edges", ["target_user_id"])
    op.create_index("ix_network_edges_target_external_id", "network_edges", ["target_external_id"])

def downgrade():
    op.drop_index("ix_network_edges_target_external_id", table_name="network_edges")
    op.drop_index("ix_network_edges_target_user_id", table_name="network_edges")
    op.drop_index("ix_network_edges_source_user_id", table_name="network_edges")
    op.drop_table("network_edges")

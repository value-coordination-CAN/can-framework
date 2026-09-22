"""agent participation: steward-bound agents, derived records and recomputations

Revision ID: 0007_agent_participation
Revises: 0006_bridge_wallet
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_agent_participation"
down_revision = "0006_bridge_wallet"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ag_agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("did", sa.String(length=400), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("steward_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contact", sa.String(length=300), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_unreviewed", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_ag_agents_did", "ag_agents", ["did"], unique=True)
    op.create_index("ix_ag_agents_steward_user_id", "ag_agents", ["steward_user_id"])

    op.create_table(
        "ag_derived_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("ag_agents.id"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("subject_ref", sa.String(length=200), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=300), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("recompute_status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by", sa.String(length=400), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", sa.String(), sa.ForeignKey("ag_derived_records.id"), nullable=True),
    )
    op.create_index("ix_ag_derived_records_agent_id", "ag_derived_records", ["agent_id"])
    op.create_index("ix_ag_derived_records_subject_ref", "ag_derived_records", ["subject_ref"])
    op.create_index("ix_ag_derived_records_output_hash", "ag_derived_records", ["output_hash"])

    op.create_table(
        "ag_recomputations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("record_id", sa.String(), sa.ForeignKey("ag_derived_records.id"), nullable=False),
        sa.Column("by_subject", sa.String(length=400), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=300), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_ag_recomputations_record_id", "ag_recomputations", ["record_id"])


def downgrade():
    op.drop_table("ag_recomputations")
    op.drop_table("ag_derived_records")
    op.drop_index("ix_ag_agents_steward_user_id", table_name="ag_agents")
    op.drop_index("ix_ag_agents_did", table_name="ag_agents")
    op.drop_table("ag_agents")

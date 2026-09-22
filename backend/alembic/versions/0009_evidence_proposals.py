"""revaluation proposals: an agent or person proposes, the holder or an attester decides

Revision ID: 0009_evidence_proposals
Revises: 0008_public_agent_register
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_evidence_proposals"
down_revision = "0008_public_agent_register"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "va_evidence_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=False),
        sa.Column("proposed_by", sa.String(length=400), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("source_ref", sa.String(length=500), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decided_by", sa.String(length=400), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("evidence_id", sa.String(), sa.ForeignKey("va_evidence.id"), nullable=True),
    )
    op.create_index("ix_va_evidence_proposals_asset_id", "va_evidence_proposals", ["asset_id"])
    op.create_index("ix_va_evidence_proposals_agent_id", "va_evidence_proposals", ["agent_id"])


def downgrade():
    op.drop_index("ix_va_evidence_proposals_agent_id", table_name="va_evidence_proposals")
    op.drop_index("ix_va_evidence_proposals_asset_id", table_name="va_evidence_proposals")
    op.drop_table("va_evidence_proposals")

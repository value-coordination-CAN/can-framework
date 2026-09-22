"""payment mandates for agents, and every payment they attempt

Revision ID: 0014_payment_mandates
Revises: 0013_agreements
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_payment_mandates"
down_revision = "0013_agreements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bw_payment_mandates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("ag_agents.id"), nullable=False),
        sa.Column("granted_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purposes", sa.JSON(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("max_per_payment", sa.Float(), nullable=False),
        sa.Column("max_total", sa.Float(), nullable=False),
        sa.Column("spent_total", sa.Float(), nullable=False),
        sa.Column("payee_user_ids", sa.JSON(), nullable=True),
        sa.Column("requires_evidence", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_bw_payment_mandates_agent_id", "bw_payment_mandates", ["agent_id"])
    op.create_index("ix_bw_payment_mandates_granted_by", "bw_payment_mandates", ["granted_by_user_id"])

    op.create_table(
        "bw_agent_payments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("mandate_id", sa.String(), sa.ForeignKey("bw_payment_mandates.id"), nullable=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("ag_agents.id"), nullable=False),
        sa.Column("payer_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payee_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("refusal_reason", sa.String(length=500), nullable=True),
        sa.Column("rail", sa.String(length=50), nullable=True),
        sa.Column("settlement_ref", sa.String(length=200), nullable=True),
        sa.Column("transaction_object", sa.JSON(), nullable=True),
    )
    op.create_index("ix_bw_agent_payments_agent_id", "bw_agent_payments", ["agent_id"])
    op.create_index("ix_bw_agent_payments_payer_user_id", "bw_agent_payments", ["payer_user_id"])


def downgrade():
    op.drop_table("bw_agent_payments")
    op.drop_table("bw_payment_mandates")

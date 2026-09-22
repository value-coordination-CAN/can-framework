"""WP-010 bridge wallet: wallets, holdings, projects, contributions, suppliers, pledges, transfers

Revision ID: 0006_bridge_wallet
Revises: 0005_value_assurance
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_bridge_wallet"
down_revision = "0005_value_assurance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bw_wallets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_bw_wallets_user_id", "bw_wallets", ["user_id"], unique=True)

    op.create_table(
        "bw_projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sponsor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("unit_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=True),
    )
    op.create_index("ix_bw_projects_sponsor_user_id", "bw_projects", ["sponsor_user_id"])

    op.create_table(
        "bw_holdings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("wallet_id", sa.String(), sa.ForeignKey("bw_wallets.id"), nullable=False),
        sa.Column("layer", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("bw_projects.id"), nullable=True),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("terms", sa.JSON(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_bw_holdings_wallet_id", "bw_holdings", ["wallet_id"])
    op.create_index("ix_bw_holdings_project_id", "bw_holdings", ["project_id"])

    op.create_table(
        "bw_contributions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("bw_projects.id"), nullable=False),
        sa.Column("contributor_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("offered_value", sa.Float(), nullable=False),
        sa.Column("accepted_value", sa.Float(), nullable=True),
        sa.Column("valuation_basis", sa.String(length=500), nullable=True),
        sa.Column("wants", sa.String(length=30), nullable=False),
        sa.Column("access_terms", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("decided_by", sa.String(length=400), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_bw_contributions_project_id", "bw_contributions", ["project_id"])
    op.create_index("ix_bw_contributions_contributor_user_id", "bw_contributions", ["contributor_user_id"])

    op.create_table(
        "bw_supplier_agreements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("bw_projects.id"), nullable=False),
        sa.Column("supplier_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("cash_share", sa.Float(), nullable=False),
        sa.Column("participation_share", sa.Float(), nullable=False),
        sa.Column("accepted_by_supplier", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
    )
    op.create_index("ix_bw_supplier_agreements_project_id", "bw_supplier_agreements", ["project_id"])
    op.create_index("ix_bw_supplier_agreements_supplier_user_id", "bw_supplier_agreements", ["supplier_user_id"])

    op.create_table(
        "bw_supplier_invoices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("agreement_id", sa.String(), sa.ForeignKey("bw_supplier_agreements.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("delivery_evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("verified_by", sa.String(length=400), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("settlement_ref", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_bw_supplier_invoices_agreement_id", "bw_supplier_invoices", ["agreement_id"])

    op.create_table(
        "bw_pledges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("holding_id", sa.String(), sa.ForeignKey("bw_holdings.id"), nullable=False),
        sa.Column("lender_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_bw_pledges_holding_id", "bw_pledges", ["holding_id"])

    op.create_table(
        "bw_transfers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("wallet_id", sa.String(), sa.ForeignKey("bw_wallets.id"), nullable=False),
        sa.Column("direction", sa.String(length=30), nullable=False),
        sa.Column("from_layer", sa.String(length=30), nullable=False),
        sa.Column("to_layer", sa.String(length=30), nullable=False),
        sa.Column("holding_id", sa.String(), sa.ForeignKey("bw_holdings.id"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("rail", sa.String(length=50), nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
    )
    op.create_index("ix_bw_transfers_wallet_id", "bw_transfers", ["wallet_id"])


def downgrade():
    op.drop_table("bw_transfers")
    op.drop_table("bw_pledges")
    op.drop_table("bw_supplier_invoices")
    op.drop_table("bw_supplier_agreements")
    op.drop_table("bw_contributions")
    op.drop_table("bw_holdings")
    op.drop_table("bw_projects")
    op.drop_table("bw_wallets")

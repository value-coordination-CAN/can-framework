"""WP-011 value assurance: assets, evidence, selective-disclosure shares, assurance runs

Revision ID: 0005_value_assurance
Revises: 0004_corrections_and_deletion
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_value_assurance"
down_revision = "0004_corrections_and_deletion"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "va_assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("holder_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("mandate", sa.JSON(), nullable=True),
    )
    op.create_index("ix_va_assets_holder_user_id", "va_assets", ["holder_user_id"])

    op.create_table(
        "va_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
        sa.Column("attester_subject", sa.String(length=400), nullable=True),
        sa.Column("self_reported", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_va_evidence_asset_id", "va_evidence", ["asset_id"])

    op.create_table(
        "va_shares",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=False),
        sa.Column("grantee_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.UniqueConstraint("asset_id", "grantee_user_id", name="uq_va_shares_asset_grantee"),
    )
    op.create_index("ix_va_shares_asset_id", "va_shares", ["asset_id"])
    op.create_index("ix_va_shares_grantee_user_id", "va_shares", ["grantee_user_id"])

    op.create_table(
        "va_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=False),
        sa.Column("triggered_by", sa.String(length=400), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("base_value", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
    )
    op.create_index("ix_va_runs_asset_id", "va_runs", ["asset_id"])


def downgrade():
    op.drop_table("va_runs")
    op.drop_table("va_shares")
    op.drop_table("va_evidence")
    op.drop_table("va_assets")

"""right to correction (entry disputes, superseded entries) and account deletion audit

Revision ID: 0004_corrections_and_deletion
Revises: 0003_authz_scoring_care_consent
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_corrections_and_deletion"
down_revision = "0003_authz_scoring_care_consent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ledger_entries", sa.Column("superseded_at", sa.DateTime(), nullable=True))
    op.add_column("ledger_entries", sa.Column("superseded_reason", sa.String(length=500), nullable=True))
    op.add_column("ledger_entries", sa.Column("supersedes_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_ledger_entries_supersedes", "ledger_entries", "ledger_entries", ["supersedes_id"], ["id"]
    )

    op.create_table(
        "entry_disputes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("entry_id", sa.String(), sa.ForeignKey("ledger_entries.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("resolved_by", sa.String(length=400), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("corrected_entry_id", sa.String(), sa.ForeignKey("ledger_entries.id"), nullable=True),
    )
    op.create_index("ix_entry_disputes_entry_id", "entry_disputes", ["entry_id"])
    op.create_index("ix_entry_disputes_user_id", "entry_disputes", ["user_id"])

    op.create_table(
        "deletion_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("deletion_records")
    op.drop_index("ix_entry_disputes_user_id", table_name="entry_disputes")
    op.drop_index("ix_entry_disputes_entry_id", table_name="entry_disputes")
    op.drop_table("entry_disputes")
    op.drop_constraint("fk_ledger_entries_supersedes", "ledger_entries", type_="foreignkey")
    op.drop_column("ledger_entries", "supersedes_id")
    op.drop_column("ledger_entries", "superseded_reason")
    op.drop_column("ledger_entries", "superseded_at")

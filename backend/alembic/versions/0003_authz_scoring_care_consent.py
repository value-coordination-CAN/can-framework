"""authorisation, explainable scoring, decisions, appeals resolution, care consent

Revision ID: 0003_authz_scoring_care_consent
Revises: 016f621224c7
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_authz_scoring_care_consent"
down_revision = "016f621224c7"
branch_labels = None
depends_on = None


def upgrade():
    # users: bind each profile to the authenticated subject (DID or OIDC sub)
    op.add_column("users", sa.Column("subject", sa.String(length=400), nullable=True))
    op.create_index("ix_users_subject", "users", ["subject"], unique=True)

    # ledger_entries: who recorded it, and whether it was self-reported.
    # Existing entries were never attested, so they are marked self-reported.
    op.add_column("ledger_entries", sa.Column("attester_subject", sa.String(length=400), nullable=True))
    op.add_column(
        "ledger_entries",
        sa.Column("self_reported", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "care_consents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("factor", sa.String(length=100), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "factor", name="uq_care_consents_user_factor"),
    )
    op.create_index("ix_care_consents_user_id", "care_consents", ["user_id"])

    op.add_column("score_snapshots", sa.Column("explanation", sa.JSON(), nullable=True))

    op.add_column("allocation_requests", sa.Column("score_snapshot_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_allocation_requests_score_snapshot",
        "allocation_requests",
        "score_snapshots",
        ["score_snapshot_id"],
        ["id"],
    )
    op.add_column("allocation_requests", sa.Column("decided_by", sa.String(length=400), nullable=True))
    op.add_column("allocation_requests", sa.Column("decided_at", sa.DateTime(), nullable=True))
    op.add_column("allocation_requests", sa.Column("decision_reason", sa.Text(), nullable=True))

    op.add_column("appeals", sa.Column("resolved_by", sa.String(length=400), nullable=True))
    op.add_column("appeals", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.add_column("appeals", sa.Column("resolution_note", sa.Text(), nullable=True))

    # LinkedIn import: stop keeping third parties' names
    op.execute("UPDATE network_edges SET display_name = NULL WHERE source_system = 'linkedin_export'")


def downgrade():
    op.drop_column("appeals", "resolution_note")
    op.drop_column("appeals", "resolved_at")
    op.drop_column("appeals", "resolved_by")
    op.drop_column("allocation_requests", "decision_reason")
    op.drop_column("allocation_requests", "decided_at")
    op.drop_column("allocation_requests", "decided_by")
    op.drop_constraint("fk_allocation_requests_score_snapshot", "allocation_requests", type_="foreignkey")
    op.drop_column("allocation_requests", "score_snapshot_id")
    op.drop_column("score_snapshots", "explanation")
    op.drop_index("ix_care_consents_user_id", table_name="care_consents")
    op.drop_table("care_consents")
    op.drop_column("ledger_entries", "self_reported")
    op.drop_column("ledger_entries", "attester_subject")
    op.drop_index("ix_users_subject", table_name="users")
    op.drop_column("users", "subject")

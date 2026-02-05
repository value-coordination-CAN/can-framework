from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ledger_type", sa.String(length=50), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("evidence_ref", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_ledger_entries_user_id", "ledger_entries", ["user_id"])

    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contribution_score", sa.Float(), nullable=False),
        sa.Column("reliability_score", sa.Float(), nullable=False),
        sa.Column("care_score", sa.Float(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
    )
    op.create_index("ix_score_snapshots_user_id", "score_snapshots", ["user_id"])

    op.create_table(
        "allocation_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pool", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_allocation_requests_user_id", "allocation_requests", ["user_id"])

    op.create_table(
        "appeals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(), sa.ForeignKey("allocation_requests.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
    )
    op.create_index("ix_appeals_user_id", "appeals", ["user_id"])
    op.create_index("ix_appeals_request_id", "appeals", ["request_id"])

def downgrade():
    op.drop_table("appeals")
    op.drop_table("allocation_requests")
    op.drop_table("score_snapshots")
    op.drop_table("ledger_entries")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

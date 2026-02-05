from alembic import op
import sqlalchemy as sa

revision = "0002_did_auth_tables"
down_revision = "0001_init"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "did_challenges",
        sa.Column("challenge", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )

    op.create_table(
        "did_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("did", sa.String(length=400), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("assurance_level", sa.String(length=50), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_did_sessions_did", "did_sessions", ["did"])

    op.create_table(
        "subject_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("did", sa.String(length=400), nullable=False),
        sa.Column("oidc_sub", sa.String(length=200), nullable=True),
        sa.Column("assurance_level", sa.String(length=50), nullable=False),
    )
    op.create_index("ix_subject_links_did", "subject_links", ["did"], unique=True)
    op.create_index("ix_subject_links_oidc_sub", "subject_links", ["oidc_sub"])

def downgrade():
    op.drop_table("subject_links")
    op.drop_table("did_sessions")
    op.drop_table("did_challenges")

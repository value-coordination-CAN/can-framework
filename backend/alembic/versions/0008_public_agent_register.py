"""public agent register: steward name publication flag

Revision ID: 0008_public_agent_register
Revises: 0007_agent_participation
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_public_agent_register"
down_revision = "0007_agent_participation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ag_agents",
        sa.Column("steward_name_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # A contact is what makes an agent answerable, so any agent registered before the
    # open register existed is marked as needing one.
    op.execute("UPDATE ag_agents SET contact = 'contact not published: ask the operator' WHERE contact IS NULL")


def downgrade():
    op.drop_column("ag_agents", "steward_name_public")

"""value map: needs and capacities, discoverable by opt-in commitment

Revision ID: 0010_value_map_items
Revises: 0009_evidence_proposals
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_value_map_items"
down_revision = "0009_evidence_proposals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vm_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("holder_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("item_class", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("available_until", sa.Date(), nullable=True),
        sa.Column("asset_id", sa.String(), sa.ForeignKey("va_assets.id"), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("discoverable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False),
    )
    op.create_index("ix_vm_items_holder_user_id", "vm_items", ["holder_user_id"])
    op.create_index("ix_vm_items_item_class", "vm_items", ["item_class"])
    op.create_index("ix_vm_items_region", "vm_items", ["region"])


def downgrade():
    op.drop_table("vm_items")

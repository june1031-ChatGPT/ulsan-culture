"""Create sources and events tables.

Revision ID: 20260808_0001
Revises:
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_item_count", sa.Integer()),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("organizer", sa.String(length=200)),
        sa.Column("venue", sa.String(length=300)),
        sa.Column("address", sa.String(length=500)),
        sa.Column("district", sa.String(length=50)),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7)),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7)),
        sa.Column("category", sa.String(length=100)),
        sa.Column("subcategory", sa.String(length=100)),
        sa.Column("original_category", sa.String(length=200)),
        sa.Column("target_text", sa.Text()),
        sa.Column("age_min", sa.Integer()),
        sa.Column("age_max", sa.Integer()),
        sa.Column("event_start", sa.DateTime(timezone=True)),
        sa.Column("event_end", sa.DateTime(timezone=True)),
        sa.Column("registration_start", sa.DateTime(timezone=True)),
        sa.Column("registration_end", sa.DateTime(timezone=True)),
        sa.Column("registration_status", sa.String(length=50)),
        sa.Column("application_method", sa.String(length=100)),
        sa.Column("participation_type", sa.String(length=100)),
        sa.Column("prerequisite_required", sa.Boolean(), nullable=False),
        sa.Column("prerequisite_text", sa.Text()),
        sa.Column("capacity", sa.Integer()),
        sa.Column("lottery_or_firstcome", sa.String(length=50)),
        sa.Column("fee", sa.Numeric(precision=12, scale=2)),
        sa.Column("is_free", sa.Boolean()),
        sa.Column("reservation_url", sa.String(length=2048)),
        sa.Column("detail_url", sa.String(length=2048)),
        sa.Column("image_url", sa.String(length=2048)),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_event_id", sa.String(length=255)),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_id", "source_event_id", name="uq_events_source_event"),
    )
    op.create_index("ix_events_category", "events", ["category"])
    op.create_index("ix_events_district", "events", ["district"])
    op.create_index("ix_events_event_start", "events", ["event_start"])
    op.create_index("ix_events_is_active", "events", ["is_active"])
    op.create_index("ix_events_registration_end", "events", ["registration_end"])
    op.create_index("ix_events_registration_start", "events", ["registration_start"])
    op.create_index("ix_events_registration_status", "events", ["registration_status"])
    op.create_index("ix_events_source_id", "events", ["source_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("sources")


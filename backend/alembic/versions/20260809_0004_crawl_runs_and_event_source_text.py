"""Add crawl runs, event source text, and last-seen provenance.

Revision ID: 20260809_0004
Revises: 20260809_0003
Create Date: 2026-08-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260809_0004"
down_revision: str | None = "20260809_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("pages_attempted", sa.Integer(), nullable=False),
        sa.Column("pages_succeeded", sa.Integer(), nullable=False),
        sa.Column("items_seen", sa.Integer(), nullable=False),
        sa.Column("items_persisted", sa.Integer(), nullable=False),
        sa.Column("items_failed", sa.Integer(), nullable=False),
        sa.Column("detail_success_count", sa.Integer(), nullable=False),
        sa.Column("detail_failure_count", sa.Integer(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("network_error_count", sa.Integer(), nullable=False),
        sa.Column("parser_error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("is_complete_snapshot", sa.Boolean(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_crawl_runs_status",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_crawl_runs_time_order",
        ),
        sa.CheckConstraint(
            "pages_attempted >= 0 AND pages_succeeded >= 0 "
            "AND pages_succeeded <= pages_attempted",
            name="ck_crawl_runs_page_counts",
        ),
        sa.CheckConstraint(
            "items_seen >= 0 AND items_persisted >= 0 AND items_failed >= 0",
            name="ck_crawl_runs_item_counts",
        ),
        sa.CheckConstraint(
            "detail_success_count >= 0 AND detail_failure_count >= 0 "
            "AND occurrence_count >= 0",
            name="ck_crawl_runs_detail_counts",
        ),
        sa.CheckConstraint(
            "network_error_count >= 0 AND parser_error_count >= 0",
            name="ck_crawl_runs_error_counts",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_crawl_runs_source_id", ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_crawl_runs_source_started", "crawl_runs", ["source_id", "started_at"]
    )
    op.create_index("ix_crawl_runs_status", "crawl_runs", ["status"])

    op.add_column("events", sa.Column("registration_period_text", sa.Text()))
    op.add_column("events", sa.Column("event_period_text", sa.Text()))
    op.add_column("events", sa.Column("capacity_text", sa.Text()))
    op.add_column("events", sa.Column("fee_text", sa.Text()))
    op.add_column("events", sa.Column("source_code", sa.String(length=20)))
    op.add_column("events", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("events", sa.Column("last_seen_run_id", sa.Integer()))
    op.create_foreign_key(
        "fk_events_last_seen_run_id",
        "events",
        "crawl_runs",
        ["last_seen_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_events_source_code", "events", ["source_code"])
    op.create_index("ix_events_last_seen_at", "events", ["last_seen_at"])
    op.create_index("ix_events_last_seen_run_id", "events", ["last_seen_run_id"])


def downgrade() -> None:
    op.drop_index("ix_events_last_seen_run_id", table_name="events")
    op.drop_index("ix_events_last_seen_at", table_name="events")
    op.drop_index("ix_events_source_code", table_name="events")
    op.drop_constraint("fk_events_last_seen_run_id", "events", type_="foreignkey")
    op.drop_column("events", "last_seen_run_id")
    op.drop_column("events", "last_seen_at")
    op.drop_column("events", "source_code")
    op.drop_column("events", "fee_text")
    op.drop_column("events", "capacity_text")
    op.drop_column("events", "event_period_text")
    op.drop_column("events", "registration_period_text")

    op.drop_index("ix_crawl_runs_status", table_name="crawl_runs")
    op.drop_index("ix_crawl_runs_source_started", table_name="crawl_runs")
    op.drop_table("crawl_runs")

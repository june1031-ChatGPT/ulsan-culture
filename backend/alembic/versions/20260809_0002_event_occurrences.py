"""Create event occurrences table.

Revision ID: 20260809_0002
Revises: 20260808_0001
Create Date: 2026-08-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260809_0002"
down_revision: str | None = "20260808_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_occurrences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer()),
        sa.Column("reserved_count", sa.Integer()),
        sa.Column("available_count", sa.Integer()),
        sa.Column("fee", sa.Numeric(precision=12, scale=2)),
        sa.Column("is_free", sa.Boolean()),
        sa.Column("application_available", sa.Boolean()),
        sa.Column("source_occurrence_id", sa.String(length=512), nullable=False),
        sa.Column("source_raw_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "available_count IS NULL OR available_count >= 0",
            name="ck_event_occurrences_available_count_nonnegative",
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity >= 0",
            name="ck_event_occurrences_capacity_nonnegative",
        ),
        sa.CheckConstraint(
            "fee IS NULL OR fee >= 0",
            name="ck_event_occurrences_fee_nonnegative",
        ),
        sa.CheckConstraint(
            "reserved_count IS NULL OR reserved_count >= 0",
            name="ck_event_occurrences_reserved_count_nonnegative",
        ),
        sa.CheckConstraint("end_at >= start_at", name="ck_event_occurrences_time_order"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "event_id",
            "source_occurrence_id",
            name="uq_event_occurrences_event_source_occurrence",
        ),
    )
    op.create_index(
        "ix_event_occurrences_event_id", "event_occurrences", ["event_id"]
    )
    op.create_index(
        "ix_event_occurrences_start_at", "event_occurrences", ["start_at"]
    )
    op.create_index(
        "ix_event_occurrences_event_id_start_at",
        "event_occurrences",
        ["event_id", "start_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_occurrences_event_id_start_at", table_name="event_occurrences"
    )
    op.drop_index("ix_event_occurrences_start_at", table_name="event_occurrences")
    op.drop_index("ix_event_occurrences_event_id", table_name="event_occurrences")
    op.drop_table("event_occurrences")

"""Preserve event date precision and add stable source item keys.

Revision ID: 20260809_0003
Revises: 20260809_0002
Create Date: 2026-08-09
"""

from collections.abc import Sequence
from hashlib import sha256
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_0003"
down_revision: str | None = "20260809_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_JSESSION_PATTERN = re.compile(r";jsessionid=[^/?#&;]*", re.IGNORECASE)


def _canonicalize_existing_url(url: str) -> str:
    """Frozen copy of the URL rules used when this migration was created."""
    absolute = urljoin("https://ulsan.go.kr", url.strip())
    parts = urlsplit(absolute)
    path = _JSESSION_PATTERN.sub("", parts.path)
    hostname = (parts.hostname or "").lower()
    scheme = parts.scheme.lower()
    netloc = parts.netloc

    if hostname in {"ulsan.go.kr", "www.ulsan.go.kr"}:
        scheme = "https"
        netloc = "ulsan.go.kr"
        if parts.port and parts.port != 443:
            netloc = f"{netloc}:{parts.port}"

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _url_item_key(url: str) -> str:
    canonical_url = _canonicalize_existing_url(url)
    return f"urlsha256:{sha256(canonical_url.encode('utf-8')).hexdigest()}"


def upgrade() -> None:
    op.add_column("events", sa.Column("event_start_date", sa.Date()))
    op.add_column("events", sa.Column("event_end_date", sa.Date()))
    op.add_column("events", sa.Column("registration_start_date", sa.Date()))
    op.add_column("events", sa.Column("registration_end_date", sa.Date()))
    op.add_column("events", sa.Column("source_item_key", sa.String(length=255)))

    connection = op.get_bind()
    events = connection.execute(
        sa.text("SELECT id, source_event_id, source_url FROM events")
    ).mappings()
    for event in events:
        item_key = (
            event["source_event_id"]
            if event["source_event_id"] is not None
            else _url_item_key(event["source_url"])
        )
        connection.execute(
            sa.text(
                "UPDATE events SET source_item_key = :source_item_key WHERE id = :id"
            ),
            {"id": event["id"], "source_item_key": item_key},
        )

    op.alter_column("events", "source_item_key", nullable=False)
    op.create_unique_constraint(
        "uq_events_source_item", "events", ["source_id", "source_item_key"]
    )

    op.create_check_constraint(
        "ck_events_event_start_precision",
        "events",
        "event_start IS NULL OR event_start_date IS NULL",
    )
    op.create_check_constraint(
        "ck_events_event_end_precision",
        "events",
        "event_end IS NULL OR event_end_date IS NULL",
    )
    op.create_check_constraint(
        "ck_events_registration_start_precision",
        "events",
        "registration_start IS NULL OR registration_start_date IS NULL",
    )
    op.create_check_constraint(
        "ck_events_registration_end_precision",
        "events",
        "registration_end IS NULL OR registration_end_date IS NULL",
    )
    op.create_check_constraint(
        "ck_events_event_datetime_order",
        "events",
        "event_end IS NULL OR event_start IS NULL OR event_end >= event_start",
    )
    op.create_check_constraint(
        "ck_events_event_date_order",
        "events",
        "event_end_date IS NULL OR event_start_date IS NULL "
        "OR event_end_date >= event_start_date",
    )
    op.create_check_constraint(
        "ck_events_registration_datetime_order",
        "events",
        "registration_end IS NULL OR registration_start IS NULL "
        "OR registration_end >= registration_start",
    )
    op.create_check_constraint(
        "ck_events_registration_date_order",
        "events",
        "registration_end_date IS NULL OR registration_start_date IS NULL "
        "OR registration_end_date >= registration_start_date",
    )

    op.create_index("ix_events_event_start_date", "events", ["event_start_date"])
    op.create_index(
        "ix_events_registration_start_date", "events", ["registration_start_date"]
    )
    op.create_index(
        "ix_events_registration_end_date", "events", ["registration_end_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_events_registration_end_date", table_name="events")
    op.drop_index("ix_events_registration_start_date", table_name="events")
    op.drop_index("ix_events_event_start_date", table_name="events")

    op.drop_constraint("ck_events_registration_date_order", "events", type_="check")
    op.drop_constraint(
        "ck_events_registration_datetime_order", "events", type_="check"
    )
    op.drop_constraint("ck_events_event_date_order", "events", type_="check")
    op.drop_constraint("ck_events_event_datetime_order", "events", type_="check")
    op.drop_constraint(
        "ck_events_registration_end_precision", "events", type_="check"
    )
    op.drop_constraint(
        "ck_events_registration_start_precision", "events", type_="check"
    )
    op.drop_constraint("ck_events_event_end_precision", "events", type_="check")
    op.drop_constraint("ck_events_event_start_precision", "events", type_="check")
    op.drop_constraint("uq_events_source_item", "events", type_="unique")

    op.drop_column("events", "source_item_key")
    op.drop_column("events", "registration_end_date")
    op.drop_column("events", "registration_start_date")
    op.drop_column("events", "event_end_date")
    op.drop_column("events", "event_start_date")

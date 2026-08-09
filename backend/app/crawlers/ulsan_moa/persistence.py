from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.crawlers.ulsan_moa.config import ULSAN_MOA_SOURCE
from app.crawlers.ulsan_moa.models import NormalizedEvent
from app.crawlers.ulsan_moa.parser import ParsedOccurrence
from app.models.event import Event
from app.models.event_occurrence import EventOccurrence
from app.models.source import Source


@dataclass(frozen=True, slots=True)
class EventUpsertResult:
    event_id: int
    event_inserted: bool
    occurrence_inserted_count: int
    occurrence_updated_count: int
    content_hash: str


EVENT_UPDATE_FIELDS = (
    "title",
    "description",
    "organizer",
    "venue",
    "address",
    "original_category",
    "target_text",
    "event_start",
    "event_end",
    "event_start_date",
    "event_end_date",
    "registration_start",
    "registration_end",
    "registration_start_date",
    "registration_end_date",
    "registration_status",
    "application_method",
    "capacity",
    "fee",
    "is_free",
    "reservation_url",
    "detail_url",
    "image_url",
    "source_event_id",
    "source_url",
    "collected_at",
    "updated_at",
    "last_verified_at",
    "content_hash",
    "is_active",
)

OCCURRENCE_UPDATE_FIELDS = (
    "start_at",
    "end_at",
    "capacity",
    "reserved_count",
    "available_count",
    "fee",
    "is_free",
    "application_available",
    "source_raw_data",
    "collected_at",
    "updated_at",
)


def build_content_hash(event: NormalizedEvent) -> str:
    """Hash stable, meaningful source data while excluding collection timestamps."""
    payload = {
        "title": event.title,
        "description": event.description,
        "organizer": event.organizer,
        "venue": event.venue,
        "address": event.address,
        "original_category": event.original_category,
        "target_text": event.target_text,
        "event_start": event.event_start,
        "event_end": event.event_end,
        "event_start_date": event.event_start_date,
        "event_end_date": event.event_end_date,
        "registration_start": event.registration_start,
        "registration_end": event.registration_end,
        "registration_start_date": event.registration_start_date,
        "registration_end_date": event.registration_end_date,
        "registration_period_text": event.registration_period_text,
        "event_period_text": event.event_period_text,
        "registration_status": event.registration_status,
        "application_method": event.application_method,
        "capacity": event.capacity,
        "capacity_text": event.capacity_text,
        "fee": event.fee,
        "fee_text": event.fee_text,
        "is_free": event.is_free,
        "reservation_url": event.reservation_url,
        "detail_url": event.detail_url,
        "image_url": event.image_url,
        "source_event_id": event.source_event_id,
        "source_item_key": event.source_item_key,
        "source_url": event.source_url,
        "occurrences": [
            _occurrence_hash_payload(occurrence)
            for occurrence in sorted(
                event.occurrences, key=lambda item: item.source_occurrence_id
            )
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_stable_json_value,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def get_or_create_source(session: Session) -> Source:
    """Create the canonical Ulsan Moa Source, or refresh its static configuration."""
    values = {
        "name": ULSAN_MOA_SOURCE.name,
        "base_url": ULSAN_MOA_SOURCE.base_url,
        "source_type": ULSAN_MOA_SOURCE.source_type,
        "is_active": True,
    }
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = postgresql_insert(Source).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[Source.name],
            set_={
                "base_url": statement.excluded.base_url,
                "source_type": statement.excluded.source_type,
                "is_active": statement.excluded.is_active,
                "updated_at": datetime.now(UTC),
            },
        ).returning(Source.id)
        source_id = session.execute(statement).scalar_one()
        return session.get_one(Source, source_id)
    if dialect_name == "sqlite":
        statement = sqlite_insert(Source).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[Source.name],
            set_={
                "base_url": statement.excluded.base_url,
                "source_type": statement.excluded.source_type,
                "is_active": statement.excluded.is_active,
                "updated_at": datetime.now(UTC),
            },
        )
        session.execute(statement)
        return session.scalars(select(Source).where(Source.name == values["name"])).one()

    source = session.scalars(select(Source).where(Source.name == values["name"])).one_or_none()
    if source is None:
        source = Source(**values)
        session.add(source)
        session.flush()
    else:
        source.base_url = values["base_url"]
        source.source_type = values["source_type"]
        source.is_active = True
    return source


def upsert_event_with_occurrences(
    session: Session,
    *,
    source_id: int,
    event: NormalizedEvent,
    collected_at: datetime | None = None,
) -> EventUpsertResult:
    """Upsert one Event graph. The caller owns the surrounding transaction."""
    observed_at = collected_at or datetime.now(UTC)
    content_hash = build_content_hash(event)
    existing_event_id = session.scalar(
        select(Event.id).where(
            Event.source_id == source_id,
            Event.source_item_key == event.source_item_key,
        )
    )
    values = _event_values(
        event,
        source_id=source_id,
        observed_at=observed_at,
        content_hash=content_hash,
    )
    event_id = _upsert_event_row(session, values)

    existing_occurrence_ids = set(
        session.scalars(
            select(EventOccurrence.source_occurrence_id).where(
                EventOccurrence.event_id == event_id,
                EventOccurrence.source_occurrence_id.in_(
                    [item.source_occurrence_id for item in event.occurrences]
                ),
            )
        ).all()
        if event.occurrences
        else ()
    )
    for occurrence in event.occurrences:
        _upsert_occurrence_row(
            session,
            _occurrence_values(
                occurrence,
                event_id=event_id,
                observed_at=observed_at,
            ),
        )
    session.flush()

    inserted_count = sum(
        occurrence.source_occurrence_id not in existing_occurrence_ids
        for occurrence in event.occurrences
    )
    return EventUpsertResult(
        event_id=event_id,
        event_inserted=existing_event_id is None,
        occurrence_inserted_count=inserted_count,
        occurrence_updated_count=len(event.occurrences) - inserted_count,
        content_hash=content_hash,
    )


def _event_values(
    event: NormalizedEvent,
    *,
    source_id: int,
    observed_at: datetime,
    content_hash: str,
) -> dict[str, Any]:
    return {
        "title": event.title,
        "description": event.description,
        "organizer": event.organizer,
        "venue": event.venue,
        "address": event.address,
        "original_category": event.original_category,
        "target_text": event.target_text,
        "event_start": event.event_start,
        "event_end": event.event_end,
        "event_start_date": event.event_start_date,
        "event_end_date": event.event_end_date,
        "registration_start": event.registration_start,
        "registration_end": event.registration_end,
        "registration_start_date": event.registration_start_date,
        "registration_end_date": event.registration_end_date,
        "registration_status": event.registration_status,
        "application_method": event.application_method,
        "capacity": event.capacity,
        "fee": event.fee,
        "is_free": event.is_free,
        "reservation_url": event.reservation_url,
        "detail_url": event.detail_url,
        "image_url": event.image_url,
        "source_id": source_id,
        "source_event_id": event.source_event_id,
        "source_item_key": event.source_item_key,
        "source_url": event.source_url,
        "collected_at": observed_at,
        "updated_at": observed_at,
        "last_verified_at": observed_at,
        "content_hash": content_hash,
        "is_active": True,
    }


def _occurrence_values(
    occurrence: ParsedOccurrence,
    *,
    event_id: int,
    observed_at: datetime,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "start_at": occurrence.start_at,
        "end_at": occurrence.end_at,
        "capacity": occurrence.capacity,
        "reserved_count": occurrence.reserved_count,
        "available_count": occurrence.available_count,
        "fee": occurrence.fee,
        "is_free": occurrence.is_free,
        "application_available": occurrence.application_available,
        "source_occurrence_id": occurrence.source_occurrence_id,
        "source_raw_data": occurrence.source_raw_data,
        "collected_at": observed_at,
        "updated_at": observed_at,
    }


def _upsert_event_row(session: Session, values: dict[str, Any]) -> int:
    dialect_name = session.get_bind().dialect.name
    insert_factory = postgresql_insert if dialect_name == "postgresql" else sqlite_insert
    if dialect_name in {"postgresql", "sqlite"}:
        statement = insert_factory(Event).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[Event.source_id, Event.source_item_key],
            set_={field: getattr(statement.excluded, field) for field in EVENT_UPDATE_FIELDS},
        ).returning(Event.id)
        return session.execute(statement).scalar_one()
    existing = session.scalars(
        select(Event).where(
            Event.source_id == values["source_id"],
            Event.source_item_key == values["source_item_key"],
        )
    ).one_or_none()
    if existing is None:
        existing = Event(**values)
        session.add(existing)
    else:
        for field in EVENT_UPDATE_FIELDS:
            setattr(existing, field, values[field])
    session.flush()
    return existing.id


def _upsert_occurrence_row(session: Session, values: dict[str, Any]) -> None:
    dialect_name = session.get_bind().dialect.name
    insert_factory = postgresql_insert if dialect_name == "postgresql" else sqlite_insert
    if dialect_name in {"postgresql", "sqlite"}:
        statement = insert_factory(EventOccurrence).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                EventOccurrence.event_id,
                EventOccurrence.source_occurrence_id,
            ],
            set_={
                field: getattr(statement.excluded, field)
                for field in OCCURRENCE_UPDATE_FIELDS
            },
        )
        session.execute(statement)
        return
    existing = session.scalars(
        select(EventOccurrence).where(
            EventOccurrence.event_id == values["event_id"],
            EventOccurrence.source_occurrence_id == values["source_occurrence_id"],
        )
    ).one_or_none()
    if existing is None:
        session.add(EventOccurrence(**values))
    else:
        for field in OCCURRENCE_UPDATE_FIELDS:
            setattr(existing, field, values[field])


def _occurrence_hash_payload(occurrence: ParsedOccurrence) -> dict[str, Any]:
    return {
        "source_occurrence_id": occurrence.source_occurrence_id,
        "start_at": occurrence.start_at,
        "end_at": occurrence.end_at,
        "capacity": occurrence.capacity,
        "reserved_count": occurrence.reserved_count,
        "available_count": occurrence.available_count,
        "fee": occurrence.fee,
        "is_free": occurrence.is_free,
        "application_available": occurrence.application_available,
    }


def _stable_json_value(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("content hash datetime values must be timezone-aware")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    raise TypeError(f"cannot serialize {type(value).__name__} for content hash")

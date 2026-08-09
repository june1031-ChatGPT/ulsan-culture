from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import JSONB, dialect
from sqlalchemy.exc import IntegrityError

from app.models.event import Event
from app.models.event_occurrence import EventOccurrence
from app.models.source import Source
from app.schemas.event_occurrence import EventOccurrenceCreate, EventOccurrenceRead


def create_event(db_session, source_event_id: str = "EXP_1") -> Event:
    source = Source(
        name=f"테스트 기관 {source_event_id}",
        base_url="https://example.com",
        source_type="website",
    )
    event = Event(
        title="가족 체험",
        source=source,
        source_event_id=source_event_id,
        source_item_key=source_event_id,
        source_url=f"https://example.com/events/{source_event_id}",
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_event_has_multiple_ordered_occurrences(db_session):
    event = create_event(db_session)
    later = EventOccurrence(
        event=event,
        start_at=datetime(2026, 8, 12, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        capacity=40,
        reserved_count=17,
        available_count=23,
        fee=Decimal("0"),
        is_free=True,
        application_available=True,
        source_occurrence_id="EXP_1:2026-08-12:326",
        source_raw_data={"oprtId": 326, "useLmtNmpr": 40, "maxPer": 4},
    )
    earlier = EventOccurrence(
        event=event,
        start_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        source_occurrence_id="EXP_1:2026-08-11:325",
        source_raw_data=[{"oprtId": 325}],
    )
    db_session.add_all([later, earlier])
    db_session.commit()

    db_session.refresh(event)

    assert len(event.occurrences) == 2
    assert [item.source_occurrence_id for item in event.occurrences] == [
        "EXP_1:2026-08-11:325",
        "EXP_1:2026-08-12:326",
    ]
    assert event.occurrences[1].source_raw_data["maxPer"] == 4
    assert event.registration_start is None
    assert event.registration_end is None


def test_source_occurrence_id_is_unique_within_event(db_session):
    event = create_event(db_session)
    occurrence_values = {
        "event_id": event.id,
        "start_at": datetime(2026, 8, 11, 10, tzinfo=UTC),
        "end_at": datetime(2026, 8, 11, 12, tzinfo=UTC),
        "source_occurrence_id": "EXP_1:2026-08-11:326",
    }
    db_session.add_all(
        [EventOccurrence(**occurrence_values), EventOccurrence(**occurrence_values)]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_occurrence_schema_requires_timezone_aware_ordered_datetimes():
    valid = EventOccurrenceCreate(
        event_id=1,
        start_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        source_occurrence_id="EXP_1:2026-08-11:326",
        source_raw_data={"aplyYn": "Y"},
    )

    assert valid.start_at.tzinfo is UTC

    with pytest.raises(ValidationError):
        EventOccurrenceCreate(
            event_id=1,
            start_at=datetime(2026, 8, 11, 10),
            end_at=datetime(2026, 8, 11, 12),
            source_occurrence_id="EXP_1:2026-08-11:326",
        )

    with pytest.raises(ValidationError):
        EventOccurrenceCreate(
            event_id=1,
            start_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
            end_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
            source_occurrence_id="EXP_1:2026-08-11:326",
        )


def test_occurrence_read_schema_from_model():
    occurrence = EventOccurrence(
        id=1,
        event_id=2,
        start_at=datetime(2026, 8, 11, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        source_occurrence_id="DAY_1:2026-08-11:10:00:12:00",
        source_raw_data={"stTm": "10:00", "enTm": "12:00"},
        collected_at=datetime(2026, 8, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 9, 1, tzinfo=UTC),
    )

    result = EventOccurrenceRead.model_validate(occurrence)

    assert result.event_id == 2
    assert result.source_raw_data == {"stTm": "10:00", "enTm": "12:00"}


def test_occurrence_table_constraints_indexes_and_postgresql_jsonb():
    table = EventOccurrence.__table__
    index_names = {index.name for index in table.indexes}
    unique_names = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    event_fk = next(iter(table.c.event_id.foreign_keys))

    assert table.c.start_at.type.timezone is True
    assert table.c.end_at.type.timezone is True
    assert event_fk.ondelete == "CASCADE"
    assert "uq_event_occurrences_event_source_occurrence" in unique_names
    assert index_names == {
        "ix_event_occurrences_event_id",
        "ix_event_occurrences_start_at",
        "ix_event_occurrences_event_id_start_at",
    }
    assert isinstance(table.c.source_raw_data.type.dialect_impl(dialect()), JSONB)
    assert set(table.c.keys()) >= {
        "event_id",
        "start_at",
        "end_at",
        "source_raw_data",
    }

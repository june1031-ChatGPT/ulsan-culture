from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.event import Event
from app.models.source import Source


def add_source(db_session, name: str) -> Source:
    source = Source(
        name=name,
        base_url=f"https://{name}.example.com",
        source_type="website",
    )
    db_session.add(source)
    db_session.flush()
    return source


def add_event(db_session, source: Source, item_key: str, **values) -> Event:
    event = Event(
        title=f"테스트 행사 {item_key}",
        source_id=source.id,
        source_item_key=item_key,
        source_url=f"https://example.com/events/{item_key}",
        **values,
    )
    db_session.add(event)
    return event


def test_exact_datetime_event_preserves_existing_datetime_columns(db_session):
    source = add_source(db_session, "exact-datetime")
    event = add_event(
        db_session,
        source,
        "LEC_1",
        source_event_id="LEC_1",
        event_start=datetime(2026, 8, 29, 14, tzinfo=UTC),
        event_end=datetime(2026, 8, 29, 16, tzinfo=UTC),
        registration_start=datetime(2026, 8, 13, 9, tzinfo=UTC),
        registration_end=datetime(2026, 8, 20, 18, tzinfo=UTC),
    )

    db_session.commit()
    db_session.refresh(event)

    assert event.event_start is not None
    assert event.registration_end is not None
    assert event.event_start_date is None
    assert event.registration_end_date is None


def test_date_only_event_uses_only_date_columns(db_session):
    source = add_source(db_session, "date-only")
    event = add_event(
        db_session,
        source,
        "urlsha256:date-only",
        event_start_date=date(2026, 8, 29),
        event_end_date=date(2026, 8, 30),
        registration_start_date=date(2026, 8, 13),
        registration_end_date=date(2026, 8, 20),
    )

    db_session.commit()
    db_session.refresh(event)

    assert event.event_start_date == date(2026, 8, 29)
    assert event.registration_end_date == date(2026, 8, 20)
    assert event.event_start is None
    assert event.registration_end is None


@pytest.mark.parametrize(
    ("datetime_field", "date_field"),
    [
        ("event_start", "event_start_date"),
        ("event_end", "event_end_date"),
        ("registration_start", "registration_start_date"),
        ("registration_end", "registration_end_date"),
    ],
)
def test_same_boundary_rejects_date_and_datetime_together(
    db_session, datetime_field: str, date_field: str
):
    source = add_source(db_session, f"precision-{datetime_field}")
    values = {
        datetime_field: datetime(2026, 8, 29, 14, tzinfo=UTC),
        date_field: date(2026, 8, 29),
    }
    add_event(db_session, source, f"invalid-{datetime_field}", **values)

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    "period",
    [
        {
            "event_start": datetime(2026, 8, 30, 14, tzinfo=UTC),
            "event_end": datetime(2026, 8, 29, 14, tzinfo=UTC),
        },
        {
            "event_start_date": date(2026, 8, 30),
            "event_end_date": date(2026, 8, 29),
        },
        {
            "registration_start": datetime(2026, 8, 20, 18, tzinfo=UTC),
            "registration_end": datetime(2026, 8, 13, 9, tzinfo=UTC),
        },
        {
            "registration_start_date": date(2026, 8, 20),
            "registration_end_date": date(2026, 8, 13),
        },
    ],
)
def test_period_rejects_end_before_start(db_session, period: dict[str, object]):
    source = add_source(db_session, f"range-{next(iter(period))}")
    add_event(db_session, source, f"invalid-{next(iter(period))}", **period)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_source_item_key_is_unique_within_one_source(db_session):
    source = add_source(db_session, "same-source")
    add_event(db_session, source, "urlsha256:same")
    add_event(db_session, source, "urlsha256:same")

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_source_item_key_is_allowed_for_different_sources(db_session):
    first_source = add_source(db_session, "first-source")
    second_source = add_source(db_session, "second-source")
    add_event(db_session, first_source, "shared-key")
    add_event(db_session, second_source, "shared-key")

    db_session.commit()

    assert db_session.query(Event).count() == 2


def test_event_table_declares_precision_range_and_identity_constraints():
    table = Event.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert table.c.event_start.type.timezone is True
    assert table.c.event_start_date.type.python_type is date
    assert table.c.source_item_key.nullable is False
    assert {
        "uq_events_source_item",
        "ck_events_event_start_precision",
        "ck_events_event_end_precision",
        "ck_events_registration_start_precision",
        "ck_events_registration_end_precision",
        "ck_events_event_datetime_order",
        "ck_events_event_date_order",
        "ck_events_registration_datetime_order",
        "ck_events_registration_date_order",
    } <= constraint_names

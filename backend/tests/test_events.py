from datetime import UTC, datetime

from app.api.routes.events import list_events
from app.main import app
from app.models.event import Event
from app.models.source import Source


def test_list_events_returns_active_events_with_separate_periods(db_session):
    source = Source(name="테스트 기관", base_url="https://example.com", source_type="website")
    db_session.add(source)
    db_session.flush()
    db_session.add(
        Event(
            title="어린이 문화 체험",
            source_id=source.id,
            source_event_id="event-1",
            source_item_key="event-1",
            source_url="https://example.com/events/1",
            event_start=datetime(2026, 8, 29, 14, tzinfo=UTC),
            event_end=datetime(2026, 8, 29, 16, tzinfo=UTC),
            registration_start=datetime(2026, 8, 13, 9, tzinfo=UTC),
            registration_end=datetime(2026, 8, 20, 18, tzinfo=UTC),
            is_active=True,
        )
    )
    db_session.commit()

    response = list_events(db_session, limit=20, offset=0)

    assert response.total == 1
    assert response.items[0].event_start != response.items[0].registration_start
    assert response.items[0].event_start_date is None
    assert response.items[0].source_item_key == "event-1"
    assert response.items[0].title == "어린이 문화 체험"
    assert "/api/events" in app.openapi()["paths"]


def test_list_events_excludes_inactive_events(db_session):
    source = Source(name="테스트 기관", base_url="https://example.com", source_type="website")
    db_session.add(source)
    db_session.flush()
    db_session.add(
        Event(
            title="숨김 행사",
            source_id=source.id,
            source_item_key="hidden",
            source_url="https://example.com/events/hidden",
            is_active=False,
        )
    )
    db_session.commit()

    response = list_events(db_session, limit=20, offset=0)

    assert response.items == []
    assert response.total == 0

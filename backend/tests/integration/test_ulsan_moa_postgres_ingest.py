import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.crawlers.ulsan_moa.models import NormalizedEvent
from app.crawlers.ulsan_moa.parser import ParsedOccurrence
from app.crawlers.ulsan_moa.persistence import (
    get_or_create_source,
    upsert_event_with_occurrences,
)
from app.database import SessionLocal, engine
from app.models.event import Event
from app.models.event_occurrence import EventOccurrence


pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL",
    ),
]


def _event() -> NormalizedEvent:
    occurrence = ParsedOccurrence(
        start_at=datetime(2026, 8, 20, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 20, 11, tzinfo=UTC),
        source_occurrence_id="EXP_INTEGRATION_TEST:2026-08-20:1",
        capacity=10,
        reserved_count=2,
        available_count=8,
        fee=Decimal("0"),
        is_free=True,
        application_available=True,
        source_raw_data={"oprtId": 1, "aplyYn": "Y"},
    )
    return NormalizedEvent(
        source_code="F400",
        resource_kind="EXP",
        title="PostgreSQL integration test",
        description=None,
        organizer="울산컬처",
        venue=None,
        address=None,
        original_category="test",
        target_text=None,
        event_start=None,
        event_end=None,
        event_start_date=None,
        event_end_date=None,
        registration_start=None,
        registration_end=None,
        registration_start_date=None,
        registration_end_date=None,
        registration_period_text=None,
        event_period_text=None,
        registration_status=None,
        application_method=None,
        capacity=10,
        capacity_text="10",
        fee=Decimal("0"),
        fee_text="무료",
        is_free=True,
        reservation_url="https://ulsan.go.kr/y/yes/test",
        detail_url="https://ulsan.go.kr/y/yes/test",
        image_url=None,
        source_event_id="EXP_INTEGRATION_TEST",
        source_item_key="EXP_INTEGRATION_TEST",
        source_url="https://ulsan.go.kr/y/yes/test",
        occurrences=(occurrence,),
    )


def test_postgresql_event_occurrence_on_conflict_upsert_rolls_back_fixture():
    assert engine.dialect.name == "postgresql"
    session = SessionLocal()
    transaction = session.begin()
    try:
        source = get_or_create_source(session)
        event = _event()
        first = upsert_event_with_occurrences(
            session, source_id=source.id, event=event
        )
        changed = replace(
            event,
            title="PostgreSQL integration test updated",
            occurrences=(replace(event.occurrences[0], reserved_count=3, available_count=7),),
        )
        second = upsert_event_with_occurrences(
            session, source_id=source.id, event=changed
        )

        assert first.event_id == second.event_id
        assert first.event_inserted is True
        assert second.event_inserted is False
        assert session.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.source_item_key == "EXP_INTEGRATION_TEST")
        ) == 1
        stored_occurrence = session.scalar(
            select(EventOccurrence).where(
                EventOccurrence.event_id == first.event_id
            )
        )
        assert stored_occurrence.reserved_count == 3
        assert stored_occurrence.source_raw_data["oprtId"] == 1
    finally:
        transaction.rollback()
        session.close()

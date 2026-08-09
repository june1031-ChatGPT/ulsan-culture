from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.crawlers.ulsan_moa.adapter import build_source_item_key
from app.crawlers.ulsan_moa.models import NormalizedEvent
from app.crawlers.ulsan_moa.parser import ParsedOccurrence
from app.crawlers.ulsan_moa.persistence import (
    build_content_hash,
    get_or_create_source,
    upsert_event_with_occurrences,
)
from app.models.event import Event
from app.models.event_occurrence import EventOccurrence
from app.models.source import Source


OBSERVED_AT = datetime(2026, 8, 9, 3, tzinfo=UTC)


def normalized_event(**changes) -> NormalizedEvent:
    base = NormalizedEvent(
        source_code="F300",
        resource_kind="LEC",
        title="과학으로 배우는 문화유산",
        description="유물 복원 체험",
        organizer="울산대곡박물관",
        venue="울산대곡박물관",
        address="울산 울주군 두동면",
        original_category="역사/과학/도서",
        target_text="6세 이상 ~ 초등학생",
        event_start=datetime(2026, 8, 13, 10, 30, tzinfo=UTC),
        event_end=datetime(2026, 8, 13, 12, tzinfo=UTC),
        event_start_date=None,
        event_end_date=None,
        registration_start=datetime(2026, 7, 1, 9, tzinfo=UTC),
        registration_end=datetime(2026, 8, 10, 17, tzinfo=UTC),
        registration_start_date=None,
        registration_end_date=None,
        registration_period_text="2026-07-01 09:00 ~ 2026-08-10 17:00",
        event_period_text="2026-08-13 10:30 ~ 2026-08-13 12:00",
        registration_status="접수중",
        application_method="인터넷",
        capacity=20,
        capacity_text="14 / 20",
        fee=Decimal("0"),
        fee_text="무료",
        is_free=True,
        reservation_url="https://ulsan.go.kr/y/yes/page.do?event=1",
        detail_url="https://ulsan.go.kr/y/yes/page.do?event=1",
        image_url="https://ulsan.go.kr/image/1.jpg",
        source_event_id="LEC_1",
        source_item_key="LEC_1",
        source_url="https://ulsan.go.kr/y/yes/page.do?event=1",
        occurrences=(),
    )
    return replace(base, **changes)


def occurrence(**changes) -> ParsedOccurrence:
    base = ParsedOccurrence(
        start_at=datetime(2026, 8, 13, 10, tzinfo=UTC),
        end_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
        source_occurrence_id="EXP_1:2026-08-13:326",
        capacity=40,
        reserved_count=17,
        available_count=23,
        fee=Decimal("0"),
        is_free=True,
        application_available=True,
        source_raw_data={"oprtId": 326, "aplyYn": "Y"},
    )
    return replace(base, **changes)


def source_id(db_session) -> int:
    source = get_or_create_source(db_session)
    identifier = source.id
    db_session.commit()
    return identifier


def test_get_or_create_source_is_idempotent_and_uses_canonical_configuration(db_session):
    first = get_or_create_source(db_session)
    db_session.commit()
    second = get_or_create_source(db_session)
    db_session.commit()

    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(Source)) == 1
    assert second.name == "울산모아 통합예약"
    assert second.base_url == "https://ulsan.go.kr/y/yes/"
    assert second.source_type == "website"


def test_event_insert_maps_all_supported_normalized_fields(db_session):
    sid = source_id(db_session)
    event = normalized_event()

    with db_session.begin():
        result = upsert_event_with_occurrences(
            db_session, source_id=sid, event=event, collected_at=OBSERVED_AT
        )

    stored = db_session.get_one(Event, result.event_id)
    assert result.event_inserted is True
    assert stored.title == event.title
    assert stored.description == event.description
    assert stored.organizer == event.organizer
    assert stored.venue == event.venue
    assert stored.address == event.address
    assert stored.original_category == event.original_category
    assert stored.target_text == event.target_text
    assert stored.event_start == event.event_start.replace(tzinfo=None)
    assert stored.event_start_date is None
    assert stored.registration_start == event.registration_start.replace(tzinfo=None)
    assert stored.registration_period_text == event.registration_period_text
    assert stored.event_period_text == event.event_period_text
    assert stored.capacity == 20
    assert stored.capacity_text == "14 / 20"
    assert stored.fee == Decimal("0.00")
    assert stored.fee_text == "무료"
    assert stored.is_free is True
    assert stored.reservation_url == event.reservation_url
    assert stored.detail_url == event.detail_url
    assert stored.image_url == event.image_url
    assert stored.source_event_id == "LEC_1"
    assert stored.source_item_key == "LEC_1"
    assert stored.source_url == event.source_url
    assert stored.collected_at == OBSERVED_AT.replace(tzinfo=None)
    assert stored.updated_at == OBSERVED_AT.replace(tzinfo=None)
    assert stored.last_verified_at == OBSERVED_AT.replace(tzinfo=None)
    assert stored.last_seen_at == OBSERVED_AT.replace(tzinfo=None)
    assert stored.source_code == "F300"
    assert stored.content_hash == build_content_hash(event)
    assert stored.is_active is True


def test_unstructured_source_text_survives_when_normalized_values_are_null(db_session):
    sid = source_id(db_session)
    event = normalized_event(
        registration_start=None,
        registration_end=None,
        registration_period_text="상시",
        capacity=None,
        capacity_text="10팀 / 가족당 최대 4명",
        fee=None,
        fee_text="회차별 상이 / 현장 별도",
        is_free=None,
    )

    with db_session.begin():
        result = upsert_event_with_occurrences(db_session, source_id=sid, event=event)

    stored = db_session.get_one(Event, result.event_id)
    assert stored.registration_start is None
    assert stored.registration_end is None
    assert stored.registration_period_text == "상시"
    assert stored.capacity is None
    assert stored.capacity_text == "10팀 / 가족당 최대 4명"
    assert stored.fee is None
    assert stored.fee_text == "회차별 상이 / 현장 별도"


def test_event_update_and_duplicate_prevention(db_session):
    sid = source_id(db_session)
    original = normalized_event()
    changed = replace(original, title="변경된 제목", capacity=30)

    with db_session.begin():
        first = upsert_event_with_occurrences(db_session, source_id=sid, event=original)
    with db_session.begin():
        second = upsert_event_with_occurrences(db_session, source_id=sid, event=changed)

    assert first.event_id == second.event_id
    assert second.event_inserted is False
    assert db_session.scalar(select(func.count()).select_from(Event)) == 1
    stored = db_session.get_one(Event, first.event_id)
    assert stored.title == "변경된 제목"
    assert stored.capacity == 30
    assert stored.content_hash == build_content_hash(changed)


def test_external_event_upsert_preserves_null_official_id(db_session):
    sid = source_id(db_session)
    external_url = "https://external.example/events/123?b=2&a=1"
    external = normalized_event(
        resource_kind="external",
        source_event_id=None,
        source_item_key=build_source_item_key(None, external_url),
        source_url=external_url,
        detail_url=external_url,
        reservation_url=external_url,
    )

    with db_session.begin():
        result = upsert_event_with_occurrences(db_session, source_id=sid, event=external)
    with db_session.begin():
        repeated = upsert_event_with_occurrences(db_session, source_id=sid, event=external)

    stored = db_session.get_one(Event, result.event_id)
    assert repeated.event_id == result.event_id
    assert stored.source_event_id is None
    assert stored.source_item_key.startswith("urlsha256:")
    assert len(stored.source_item_key) == len("urlsha256:") + 64


def test_date_only_event_never_invents_datetimes(db_session):
    sid = source_id(db_session)
    event = normalized_event(
        event_start=None,
        event_end=None,
        event_start_date=date(2026, 8, 13),
        event_end_date=date(2026, 8, 14),
        registration_start=None,
        registration_end=None,
        registration_start_date=date(2026, 7, 1),
        registration_end_date=date(2026, 8, 10),
    )

    with db_session.begin():
        result = upsert_event_with_occurrences(db_session, source_id=sid, event=event)

    stored = db_session.get_one(Event, result.event_id)
    assert stored.event_start is None
    assert stored.event_end is None
    assert stored.event_start_date == date(2026, 8, 13)
    assert stored.event_end_date == date(2026, 8, 14)
    assert stored.registration_start is None
    assert stored.registration_start_date == date(2026, 7, 1)


def test_occurrence_insert_then_update_without_duplicate(db_session):
    sid = source_id(db_session)
    first_event = normalized_event(
        resource_kind="EXP", occurrences=(occurrence(),)
    )
    changed_occurrence = occurrence(
        reserved_count=20,
        available_count=20,
        application_available=False,
        source_raw_data={"aplyYn": "N", "oprtId": 326},
    )
    second_event = replace(first_event, occurrences=(changed_occurrence,))

    with db_session.begin():
        first = upsert_event_with_occurrences(db_session, source_id=sid, event=first_event)
    with db_session.begin():
        second = upsert_event_with_occurrences(db_session, source_id=sid, event=second_event)

    assert first.occurrence_inserted_count == 1
    assert second.occurrence_updated_count == 1
    assert db_session.scalar(select(func.count()).select_from(EventOccurrence)) == 1
    stored = db_session.scalar(select(EventOccurrence))
    assert stored.reserved_count == 20
    assert stored.available_count == 20
    assert stored.application_available is False
    assert stored.source_raw_data == {"aplyYn": "N", "oprtId": 326}


def test_event_and_occurrences_roll_back_as_one_transaction(db_session):
    sid = source_id(db_session)
    invalid = normalized_event(
        source_event_id="EXP_ROLLBACK",
        source_item_key="EXP_ROLLBACK",
        occurrences=(
            occurrence(
                source_occurrence_id="EXP_ROLLBACK:1",
                start_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
                end_at=datetime(2026, 8, 13, 10, tzinfo=UTC),
            ),
        ),
    )

    with pytest.raises(IntegrityError):
        with db_session.begin():
            upsert_event_with_occurrences(db_session, source_id=sid, event=invalid)

    assert db_session.scalar(
        select(func.count()).select_from(Event).where(Event.source_item_key == "EXP_ROLLBACK")
    ) == 0
    assert db_session.scalar(select(func.count()).select_from(EventOccurrence)) == 0


def test_content_hash_is_stable_and_occurrence_order_independent():
    first = occurrence(source_occurrence_id="EXP_1:b")
    second = occurrence(source_occurrence_id="EXP_1:a")
    event = normalized_event(occurrences=(first, second))
    reordered = replace(event, occurrences=(second, first))

    assert build_content_hash(event) == build_content_hash(reordered)
    assert build_content_hash(event) == build_content_hash(event)
    assert build_content_hash(event) != build_content_hash(replace(event, title="변경"))

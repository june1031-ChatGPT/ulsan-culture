from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.crawlers.ulsan_moa.ingest import ingest_collected_page
from app.crawlers.ulsan_moa.models import DryRunResult, DryRunSummary
from app.models.base import Base
from app.models.event import Event
from app.models.event_occurrence import EventOccurrence
from app.models.source import Source
from tests.test_ulsan_moa_persistence import normalized_event, occurrence


def test_batch_keeps_successful_event_and_rolls_back_only_failed_event():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    good = normalized_event(source_event_id="LEC_GOOD", source_item_key="LEC_GOOD")
    bad = normalized_event(
        source_event_id="EXP_BAD",
        source_item_key="EXP_BAD",
        occurrences=(
            occurrence(
                source_occurrence_id="EXP_BAD:1",
                start_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
                end_at=datetime(2026, 8, 13, 10, tzinfo=UTC),
            ),
        ),
    )
    collection = DryRunResult(
        summary=DryRunSummary(
            source="F300",
            page=1,
            list_count=2,
            internal_count=2,
            external_count=0,
            lec_count=1,
            exp_count=1,
            day_count=0,
            detail_success_count=2,
            detail_failure_count=0,
            occurrence_count=1,
            parser_errors=(),
            network_errors=(),
            request_counts={},
            samples=(),
        ),
        events=(good, bad),
    )

    summary = ingest_collected_page(collection, session_factory=session_factory)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 1
        assert session.scalar(select(func.count()).select_from(EventOccurrence)) == 0
        source = session.scalar(select(Source))
        assert source.last_item_count == 2
        assert source.last_success_at is None
        assert source.error_count == 1
        assert "EXP_BAD" in source.error_message
    assert summary.persisted_count == 1
    assert summary.failed_count == 1
    assert summary.event_inserted_count == 1
    engine.dispose()


def test_source_success_status_is_batch_level_and_resets_errors():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    event = normalized_event()
    summary_data = DryRunSummary(
        source="F300",
        page=1,
        list_count=1,
        internal_count=1,
        external_count=0,
        lec_count=1,
        exp_count=0,
        day_count=0,
        detail_success_count=1,
        detail_failure_count=0,
        occurrence_count=0,
        parser_errors=(),
        network_errors=(),
        request_counts={},
        samples=(),
    )
    collection = DryRunResult(summary=summary_data, events=(event,))
    checked_at = datetime(2026, 8, 9, 5, tzinfo=UTC)

    first = ingest_collected_page(
        collection, session_factory=session_factory, observed_at=checked_at
    )
    second = ingest_collected_page(
        replace(collection, events=(replace(event, title="갱신"),)),
        session_factory=session_factory,
        observed_at=checked_at,
    )

    with Session(engine) as session:
        source = session.scalar(select(Source))
        assert source.last_checked_at == checked_at.replace(tzinfo=None)
        assert source.last_success_at == checked_at.replace(tzinfo=None)
        assert source.last_item_count == 1
        assert source.error_count == 0
        assert source.error_message is None
        assert session.scalar(select(func.count()).select_from(Event)) == 1
    assert first.event_inserted_count == 1
    assert second.event_updated_count == 1
    engine.dispose()

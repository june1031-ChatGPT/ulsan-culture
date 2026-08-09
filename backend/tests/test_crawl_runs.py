import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.crawlers.ulsan_moa.ingest import (
    collect_and_ingest_all_pages,
    ingest_collected_pages,
)
from app.crawlers.ulsan_moa.models import FullCollectionResult, FullCollectionSummary
from app.crawlers.ulsan_moa.persistence import get_or_create_source
from app.crawlers.ulsan_moa.run_management import (
    create_crawl_run,
    deactivate_stale_events,
    finish_crawl_run,
)
from app.models.base import Base
from app.models.crawl_run import CrawlRun
from app.models.event import Event
from app.models.source import Source
from tests.test_ulsan_moa_persistence import normalized_event


STARTED = datetime(2026, 8, 9, 1, tzinfo=UTC)
FINISHED = datetime(2026, 8, 9, 2, tzinfo=UTC)


def event(source_id: int, key: str, source_code: str) -> Event:
    return Event(
        title=key,
        source_id=source_id,
        source_event_id=key,
        source_item_key=key,
        source_url=f"https://example.com/{key}",
        source_code=source_code,
        is_active=True,
    )


def finish(
    session: Session,
    run_id: int,
    *,
    status: str,
    complete: bool,
) -> CrawlRun:
    return finish_crawl_run(
        session,
        crawl_run_id=run_id,
        status=status,
        finished_at=FINISHED,
        pages_attempted=2,
        pages_succeeded=2 if complete else 1,
        items_seen=2,
        items_persisted=1,
        items_failed=0,
        detail_success_count=1,
        detail_failure_count=0,
        occurrence_count=0,
        network_error_count=0 if complete else 1,
        parser_error_count=0,
        error_message=None if complete else "page 2 timeout",
        is_complete_snapshot=complete,
    )


def test_partial_run_cannot_deactivate_existing_events(db_session):
    source = get_or_create_source(db_session)
    db_session.flush()
    old = event(source.id, "LEC_OLD", "F300")
    db_session.add(old)
    run = create_crawl_run(
        db_session, source_id=source.id, scope="F300", started_at=STARTED
    )
    db_session.flush()
    finish(db_session, run.id, status="partial", complete=False)

    with pytest.raises(ValueError, match="complete snapshot"):
        deactivate_stale_events(db_session, crawl_run_id=run.id)

    db_session.flush()
    assert old.is_active is True


def test_complete_snapshot_soft_deactivates_only_unseen_events_in_exact_scope(
    db_session,
):
    source = get_or_create_source(db_session)
    db_session.flush()
    stale = event(source.id, "LEC_STALE", "F300")
    seen = event(source.id, "LEC_SEEN", "F300")
    other_scope = event(source.id, "EXP_OTHER", "F400")
    db_session.add_all([stale, seen, other_scope])
    run = create_crawl_run(
        db_session, source_id=source.id, scope="F300", started_at=STARTED
    )
    db_session.flush()
    seen.last_seen_at = FINISHED
    seen.last_seen_run_id = run.id
    finish(db_session, run.id, status="success", complete=True)

    count = deactivate_stale_events(db_session, crawl_run_id=run.id)
    db_session.flush()

    assert count == 1
    assert stale.is_active is False
    assert seen.is_active is True
    assert other_scope.is_active is True


def test_complete_collection_ingest_records_stats_last_seen_and_applies_safe_stale():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        source = get_or_create_source(session)
        session.flush()
        session.add_all(
            [
                event(source.id, "LEC_STALE", "F300"),
                event(source.id, "EXP_KEEP", "F400"),
            ]
        )

    collected_event = normalized_event(
        source_event_id="LEC_CURRENT", source_item_key="LEC_CURRENT"
    )
    collection = FullCollectionResult(
        summary=FullCollectionSummary(
            source="F300",
            page_size=12,
            started_at=STARTED,
            finished_at=FINISHED,
            status="success",
            pages_attempted=2,
            pages_succeeded=2,
            items_seen=1,
            detail_success_count=1,
            detail_failure_count=0,
            occurrence_count=0,
            network_errors=(),
            parser_errors=(),
            request_counts={"list": 2, "detail": 1, "total": 3},
            is_complete_snapshot=True,
            stop_reason="short-page",
        ),
        pages=(),
        events=(collected_event,),
    )

    summary = ingest_collected_pages(collection, session_factory=factory)

    with factory() as session:
        run = session.get_one(CrawlRun, summary.crawl_run_id)
        current = session.scalar(
            select(Event).where(Event.source_item_key == "LEC_CURRENT")
        )
        stale = session.scalar(
            select(Event).where(Event.source_item_key == "LEC_STALE")
        )
        other = session.scalar(
            select(Event).where(Event.source_item_key == "EXP_KEEP")
        )
        assert run.status == "success"
        assert run.pages_attempted == 2
        assert run.pages_succeeded == 2
        assert run.items_seen == 1
        assert run.items_persisted == 1
        assert run.is_complete_snapshot is True
        assert current.last_seen_run_id == run.id
        assert current.last_seen_at == FINISHED.replace(tzinfo=None)
        assert stale.is_active is False
        assert other.is_active is True
    assert summary.stale_deactivated_count == 1
    engine.dispose()


def test_full_collection_orchestrator_records_unexpected_failure_before_reraising():
    class BrokenAdapter:
        async def collect_all_pages(self, source, **options):
            raise RuntimeError("fixture crash")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with pytest.raises(RuntimeError, match="fixture crash"):
        asyncio.run(
            collect_and_ingest_all_pages(
                BrokenAdapter(), "F300", session_factory=factory
            )
        )

    with factory() as session:
        run = session.scalar(select(CrawlRun))
        source = session.scalar(select(Source))
        assert run.status == "failed"
        assert run.is_complete_snapshot is False
        assert "fixture crash" in run.error_message
        assert source.last_success_at is None
        assert source.error_count == 1
    engine.dispose()

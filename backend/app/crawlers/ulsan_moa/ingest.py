from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable, Iterable

from sqlalchemy.orm import Session

from app.crawlers.ulsan_moa.models import (
    DryRunResult,
    FullCollectionResult,
    NormalizedEvent,
)
from app.crawlers.ulsan_moa.client import SourceCode
from app.crawlers.ulsan_moa.persistence import (
    EventUpsertResult,
    get_or_create_source,
    mark_existing_event_seen,
    upsert_event_with_occurrences,
)
from app.crawlers.ulsan_moa.run_management import (
    create_crawl_run,
    deactivate_stale_events,
    finish_crawl_run,
)
from app.models.source import Source

if TYPE_CHECKING:
    from app.crawlers.ulsan_moa.adapter import UlsanMoaAdapter


SessionFactory = Callable[[], Session]


@dataclass(frozen=True, slots=True)
class IngestSummary:
    source: str
    page: int | None
    fetched_count: int
    persisted_count: int
    event_inserted_count: int
    event_updated_count: int
    occurrence_inserted_count: int
    occurrence_updated_count: int
    failed_count: int
    errors: tuple[str, ...]
    crawl_run_id: int
    run_status: str
    is_complete_snapshot: bool
    stale_deactivated_count: int = 0


def ingest_collected_page(
    result: DryRunResult,
    *,
    session_factory: SessionFactory,
    observed_at: datetime | None = None,
) -> IngestSummary:
    """Persist one page and record it as a non-snapshot CrawlRun.

    One malformed Event graph cannot roll back the other events. A single page
    can have a successful run status, but it is never a complete snapshot and
    therefore can never trigger stale processing.
    """
    checked_at = observed_at or datetime.now(UTC)
    with session_factory() as session, session.begin():
        source_id = get_or_create_source(session).id
        run_id = create_crawl_run(
            session,
            source_id=source_id,
            scope=f"{result.summary.source}:page-{result.summary.page}-test",
            started_at=checked_at,
        ).id

    upserts, persistence_errors = _persist_events(
        result.events,
        session_factory=session_factory,
        source_id=source_id,
        crawl_run_id=run_id,
        observed_at=checked_at,
    )
    collection_errors = _page_collection_errors(result)
    errors = (*collection_errors, *persistence_errors)
    status = "success" if not errors else "partial" if upserts else "failed"

    with session_factory() as session, session.begin():
        finish_crawl_run(
            session,
            crawl_run_id=run_id,
            status=status,
            finished_at=checked_at,
            pages_attempted=1,
            pages_succeeded=int(result.summary.list_page_succeeded),
            items_seen=result.summary.list_count,
            items_persisted=len(upserts),
            items_failed=len(persistence_errors),
            detail_success_count=result.summary.detail_success_count,
            detail_failure_count=result.summary.detail_failure_count,
            occurrence_count=result.summary.occurrence_count,
            network_error_count=len(result.summary.network_errors),
            parser_error_count=len(result.summary.parser_errors),
            error_message=" | ".join(errors) or None,
            is_complete_snapshot=False,
            summary={"request_counts": result.summary.request_counts},
        )
    _update_source_status(
        session_factory,
        source_id=source_id,
        checked_at=checked_at,
        item_count=result.summary.list_count,
        errors=errors,
    )
    return _build_ingest_summary(
        source=result.summary.source,
        page=result.summary.page,
        fetched_count=result.summary.list_count,
        upserts=upserts,
        persistence_errors=persistence_errors,
        errors=errors,
        crawl_run_id=run_id,
        run_status=status,
        is_complete_snapshot=False,
    )


def ingest_collected_pages(
    result: FullCollectionResult,
    *,
    session_factory: SessionFactory,
    apply_stale: bool = True,
) -> IngestSummary:
    """Persist an already collected multi-page candidate."""
    summary = result.summary
    with session_factory() as session, session.begin():
        source_id = get_or_create_source(session).id
        run_id = create_crawl_run(
            session,
            source_id=source_id,
            scope=summary.source,
            started_at=summary.started_at,
        ).id
    return _ingest_collected_pages(
        result,
        session_factory=session_factory,
        source_id=source_id,
        run_id=run_id,
        apply_stale=apply_stale,
    )


async def collect_and_ingest_all_pages(
    adapter: "UlsanMoaAdapter",
    source: SourceCode,
    *,
    session_factory: SessionFactory,
    apply_stale: bool = True,
    **collection_options,
) -> IngestSummary:
    """Create the running record before any full-page network traversal.

    This is deliberately not connected to the CLI yet. Calling it is an explicit
    future operational action, while tests can keep using DB-free collection.
    """
    started_at = datetime.now(UTC)
    with session_factory() as session, session.begin():
        source_id = get_or_create_source(session).id
        run_id = create_crawl_run(
            session,
            source_id=source_id,
            scope=source,
            started_at=started_at,
        ).id
    try:
        result = await adapter.collect_all_pages(source, **collection_options)
    except Exception as exc:
        finished_at = datetime.now(UTC)
        error = f"unexpected collection failure: {type(exc).__name__}: {exc}"
        with session_factory() as session, session.begin():
            finish_crawl_run(
                session,
                crawl_run_id=run_id,
                status="failed",
                finished_at=finished_at,
                pages_attempted=0,
                pages_succeeded=0,
                items_seen=0,
                items_persisted=0,
                items_failed=0,
                detail_success_count=0,
                detail_failure_count=0,
                occurrence_count=0,
                network_error_count=0,
                parser_error_count=0,
                error_message=error,
                is_complete_snapshot=False,
            )
        _update_source_status(
            session_factory,
            source_id=source_id,
            checked_at=finished_at,
            item_count=0,
            errors=(error,),
        )
        raise
    return _ingest_collected_pages(
        result,
        session_factory=session_factory,
        source_id=source_id,
        run_id=run_id,
        apply_stale=apply_stale,
    )


def _ingest_collected_pages(
    result: FullCollectionResult,
    *,
    session_factory: SessionFactory,
    source_id: int,
    run_id: int,
    apply_stale: bool,
) -> IngestSummary:
    """Persist and finalize a pre-created full-snapshot CrawlRun."""
    summary = result.summary

    upserts, persistence_errors = _persist_events(
        result.events,
        session_factory=session_factory,
        source_id=source_id,
        crawl_run_id=run_id,
        observed_at=summary.finished_at,
    )
    collection_errors = (
        *(f"parser: {error}" for error in summary.parser_errors),
        *(f"network: {error}" for error in summary.network_errors),
    )
    errors = (*collection_errors, *persistence_errors)
    status = (
        "success"
        if summary.status == "success" and not persistence_errors
        else "partial"
        if summary.pages_succeeded > 0 or upserts
        else "failed"
    )
    complete = bool(
        summary.is_complete_snapshot
        and status == "success"
        and not errors
        and summary.pages_attempted == summary.pages_succeeded
    )
    with session_factory() as session, session.begin():
        finish_crawl_run(
            session,
            crawl_run_id=run_id,
            status=status,
            finished_at=summary.finished_at,
            pages_attempted=summary.pages_attempted,
            pages_succeeded=summary.pages_succeeded,
            items_seen=summary.items_seen,
            items_persisted=len(upserts),
            items_failed=len(persistence_errors),
            detail_success_count=summary.detail_success_count,
            detail_failure_count=summary.detail_failure_count,
            occurrence_count=summary.occurrence_count,
            network_error_count=len(summary.network_errors),
            parser_error_count=len(summary.parser_errors),
            error_message=" | ".join(errors) or None,
            is_complete_snapshot=complete,
            summary={
                "page_size": summary.page_size,
                "request_counts": summary.request_counts,
                "stop_reason": summary.stop_reason,
            },
        )

    stale_count = 0
    if apply_stale and complete:
        with session_factory() as session, session.begin():
            stale_count = deactivate_stale_events(session, crawl_run_id=run_id)

    _update_source_status(
        session_factory,
        source_id=source_id,
        checked_at=summary.finished_at,
        item_count=summary.items_seen,
        errors=errors,
    )
    return _build_ingest_summary(
        source=summary.source,
        page=None,
        fetched_count=summary.items_seen,
        upserts=upserts,
        persistence_errors=persistence_errors,
        errors=errors,
        crawl_run_id=run_id,
        run_status=status,
        is_complete_snapshot=complete,
        stale_deactivated_count=stale_count,
    )


def _persist_events(
    events: Iterable[NormalizedEvent],
    *,
    session_factory: SessionFactory,
    source_id: int,
    crawl_run_id: int,
    observed_at: datetime,
) -> tuple[list[EventUpsertResult], list[str]]:
    upserts: list[EventUpsertResult] = []
    errors: list[str] = []
    for event in events:
        try:
            with session_factory() as session, session.begin():
                # A failed internal detail request proves presence but not that
                # detail fields became null. Preserve an existing good record.
                if not event.detail_complete:
                    existing_id = mark_existing_event_seen(
                        session,
                        source_id=source_id,
                        source_item_key=event.source_item_key,
                        observed_at=observed_at,
                        crawl_run_id=crawl_run_id,
                    )
                    if existing_id is not None:
                        upserts.append(
                            EventUpsertResult(existing_id, False, 0, 0, "")
                        )
                        continue
                upserts.append(
                    upsert_event_with_occurrences(
                        session,
                        source_id=source_id,
                        event=event,
                        collected_at=observed_at,
                        crawl_run_id=crawl_run_id,
                    )
                )
        except Exception as exc:
            errors.append(f"{event.source_item_key}: {type(exc).__name__}: {exc}")
            # Seeing the list item is still valid evidence even when its graph
            # fails to persist. Touch only a pre-existing row in a new txn.
            try:
                with session_factory() as session, session.begin():
                    mark_existing_event_seen(
                        session,
                        source_id=source_id,
                        source_item_key=event.source_item_key,
                        observed_at=observed_at,
                        crawl_run_id=crawl_run_id,
                    )
            except Exception as touch_exc:
                errors[-1] += (
                    f"; last_seen touch failed: {type(touch_exc).__name__}: "
                    f"{touch_exc}"
                )
    return upserts, errors


def _page_collection_errors(result: DryRunResult) -> tuple[str, ...]:
    return (
        *(f"parser: {error}" for error in result.summary.parser_errors),
        *(f"network: {error}" for error in result.summary.network_errors),
    )


def _build_ingest_summary(
    *,
    source: str,
    page: int | None,
    fetched_count: int,
    upserts: list[EventUpsertResult],
    persistence_errors: list[str],
    errors: tuple[str, ...],
    crawl_run_id: int,
    run_status: str,
    is_complete_snapshot: bool,
    stale_deactivated_count: int = 0,
) -> IngestSummary:
    inserted = sum(item.event_inserted for item in upserts)
    return IngestSummary(
        source=source,
        page=page,
        fetched_count=fetched_count,
        persisted_count=len(upserts),
        event_inserted_count=inserted,
        event_updated_count=len(upserts) - inserted,
        occurrence_inserted_count=sum(
            item.occurrence_inserted_count for item in upserts
        ),
        occurrence_updated_count=sum(
            item.occurrence_updated_count for item in upserts
        ),
        failed_count=len(persistence_errors),
        errors=errors,
        crawl_run_id=crawl_run_id,
        run_status=run_status,
        is_complete_snapshot=is_complete_snapshot,
        stale_deactivated_count=stale_deactivated_count,
    )


def _update_source_status(
    session_factory: SessionFactory,
    *,
    source_id: int,
    checked_at: datetime,
    item_count: int,
    errors: tuple[str, ...],
) -> None:
    with session_factory() as session, session.begin():
        source = session.get_one(Source, source_id)
        source.last_checked_at = checked_at
        source.last_item_count = item_count
        if errors:
            source.error_count += 1
            source.error_message = " | ".join(errors)[:10000]
        else:
            source.last_success_at = checked_at
            source.error_count = 0
            source.error_message = None

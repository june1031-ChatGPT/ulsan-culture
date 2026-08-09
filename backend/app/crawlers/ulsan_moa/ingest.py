from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.crawlers.ulsan_moa.models import DryRunResult
from app.crawlers.ulsan_moa.persistence import (
    EventUpsertResult,
    get_or_create_source,
    upsert_event_with_occurrences,
)
from app.models.source import Source


SessionFactory = Callable[[], Session]


@dataclass(frozen=True, slots=True)
class IngestSummary:
    source: str
    page: int
    fetched_count: int
    persisted_count: int
    event_inserted_count: int
    event_updated_count: int
    occurrence_inserted_count: int
    occurrence_updated_count: int
    failed_count: int
    errors: tuple[str, ...]


def ingest_collected_page(
    result: DryRunResult,
    *,
    session_factory: SessionFactory,
    observed_at: datetime | None = None,
) -> IngestSummary:
    """Persist one collected page using one transaction per Event graph.

    Batch collection and Source status are separate from the Event transactions, so
    one malformed item does not roll back other successfully stored items.
    """
    checked_at = observed_at or datetime.now(UTC)
    with session_factory() as session, session.begin():
        source_id = get_or_create_source(session).id

    upserts: list[EventUpsertResult] = []
    persistence_errors: list[str] = []
    for event in result.events:
        try:
            with session_factory() as session, session.begin():
                upserts.append(
                    upsert_event_with_occurrences(
                        session,
                        source_id=source_id,
                        event=event,
                        collected_at=checked_at,
                    )
                )
        except Exception as exc:
            persistence_errors.append(
                f"{event.source_item_key}: {type(exc).__name__}: {exc}"
            )

    collection_errors = [
        *(f"parser: {error}" for error in result.summary.parser_errors),
        *(f"network: {error}" for error in result.summary.network_errors),
    ]
    errors = (*collection_errors, *persistence_errors)
    _update_source_status(
        session_factory,
        source_id=source_id,
        checked_at=checked_at,
        item_count=result.summary.list_count,
        errors=errors,
    )

    inserted = sum(item.event_inserted for item in upserts)
    return IngestSummary(
        source=result.summary.source,
        page=result.summary.page,
        fetched_count=result.summary.list_count,
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

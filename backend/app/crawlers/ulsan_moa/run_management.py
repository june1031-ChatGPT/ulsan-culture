from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models.crawl_run import CrawlRun
from app.models.event import Event


CrawlRunStatus = Literal["running", "success", "partial", "failed"]


def create_crawl_run(
    session: Session,
    *,
    source_id: int,
    scope: str,
    started_at: datetime | None = None,
) -> CrawlRun:
    run = CrawlRun(
        source_id=source_id,
        scope=scope,
        started_at=started_at or datetime.now(UTC),
        status="running",
        is_complete_snapshot=False,
    )
    session.add(run)
    session.flush()
    return run


def finish_crawl_run(
    session: Session,
    *,
    crawl_run_id: int,
    status: Literal["success", "partial", "failed"],
    finished_at: datetime | None = None,
    pages_attempted: int,
    pages_succeeded: int,
    items_seen: int,
    items_persisted: int,
    items_failed: int,
    detail_success_count: int,
    detail_failure_count: int,
    occurrence_count: int,
    network_error_count: int,
    parser_error_count: int,
    error_message: str | None,
    is_complete_snapshot: bool,
    summary: dict[str, Any] | None = None,
) -> CrawlRun:
    run = session.get_one(CrawlRun, crawl_run_id)
    if run.status != "running":
        raise ValueError("only a running crawl run can be finalized")
    run.finished_at = finished_at or datetime.now(UTC)
    run.status = status
    run.pages_attempted = pages_attempted
    run.pages_succeeded = pages_succeeded
    run.items_seen = items_seen
    run.items_persisted = items_persisted
    run.items_failed = items_failed
    run.detail_success_count = detail_success_count
    run.detail_failure_count = detail_failure_count
    run.occurrence_count = occurrence_count
    run.network_error_count = network_error_count
    run.parser_error_count = parser_error_count
    run.error_message = error_message[:10000] if error_message else None
    run.is_complete_snapshot = is_complete_snapshot
    run.summary = summary
    session.flush()
    return run


def stale_source_codes(run: CrawlRun) -> tuple[str, ...]:
    """Return the exact Event partitions a proven full scope may affect."""
    if run.scope == "F300":
        return ("F300",)
    if run.scope == "F400":
        return ("F400",)
    if run.scope in {"F300:F400", "full"}:
        return ("F300", "F400")
    return ()


def can_deactivate_stale(run: CrawlRun) -> bool:
    return bool(
        run.status == "success"
        and run.is_complete_snapshot
        and run.finished_at is not None
        and stale_source_codes(run)
    )


def deactivate_stale_events(session: Session, *, crawl_run_id: int) -> int:
    """Soft-deactivate unseen rows only for a proven, successful full snapshot."""
    run = session.get_one(CrawlRun, crawl_run_id)
    source_codes = stale_source_codes(run)
    if not can_deactivate_stale(run):
        raise ValueError(
            "stale processing requires a finished successful complete snapshot "
            "with an exact full-list scope"
        )
    statement = (
        update(Event)
        .where(
            Event.source_id == run.source_id,
            Event.source_code.in_(source_codes),
            or_(
                Event.last_seen_run_id.is_(None),
                Event.last_seen_run_id != run.id,
            ),
            Event.is_active.is_(True),
        )
        .values(is_active=False, updated_at=run.finished_at)
    )
    return session.execute(statement).rowcount or 0

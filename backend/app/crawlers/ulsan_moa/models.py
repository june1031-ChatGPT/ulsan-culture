from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from app.crawlers.ulsan_moa.parser import ParsedOccurrence, ResourceKind


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    """DB-free intermediate object preserving the source's date precision."""

    source_code: Literal["F300", "F400"]
    resource_kind: ResourceKind
    title: str
    description: str | None
    organizer: str | None
    venue: str | None
    address: str | None
    original_category: str | None
    target_text: str | None
    event_start: date | datetime | None
    event_end: date | datetime | None
    registration_start: date | datetime | None
    registration_end: date | datetime | None
    registration_period_text: str | None
    event_period_text: str | None
    registration_status: str | None
    application_method: str | None
    capacity: int | None
    capacity_text: str | None
    fee: Decimal | None
    fee_text: str | None
    is_free: bool | None
    reservation_url: str
    detail_url: str
    image_url: str | None
    source_event_id: str | None
    source_url: str
    occurrences: tuple[ParsedOccurrence, ...]


@dataclass(frozen=True, slots=True)
class DryRunSummary:
    source: Literal["F300", "F400"]
    page: int
    list_count: int
    internal_count: int
    external_count: int
    lec_count: int
    exp_count: int
    day_count: int
    detail_success_count: int
    detail_failure_count: int
    occurrence_count: int
    parser_errors: tuple[str, ...]
    network_errors: tuple[str, ...]
    request_counts: dict[str, int]
    samples: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class DryRunResult:
    summary: DryRunSummary
    events: tuple[NormalizedEvent, ...]

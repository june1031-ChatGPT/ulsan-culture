from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Protocol, cast
from urllib.parse import parse_qs, urlsplit

from app.crawlers.ulsan_moa.client import SourceCode, UlsanMoaNetworkError
from app.crawlers.ulsan_moa.models import DryRunResult, DryRunSummary, NormalizedEvent
from app.crawlers.ulsan_moa.parser import (
    ParsedDetail,
    ParsedListItem,
    ParsedOccurrence,
    UlsanMoaParseError,
    canonicalize_url,
    parse_day_slots,
    parse_detail,
    parse_exp_slots,
    parse_list,
)


class UlsanMoaClientProtocol(Protocol):
    @property
    def request_counts(self) -> dict[str, int]: ...

    async def fetch_list(
        self, source: SourceCode, *, page: int = 1, page_size: int = 12
    ) -> str: ...

    async def fetch_detail(self, detail_url: str) -> str: ...

    async def fetch_exp_slots(
        self, *, rsrc_unq_id: str, rsrc_ymd: date, mnu_code: str
    ) -> str: ...

    async def fetch_day_slots(
        self, *, rsrc_unq_id: str, rsrc_ymd: date, mnu_code: str = "F601"
    ) -> str: ...


class UlsanMoaAdapter:
    """Collects one page into DB-free normalized objects."""

    def __init__(self, client: UlsanMoaClientProtocol) -> None:
        self.client = client

    async def dry_run(
        self, source: SourceCode, *, page: int = 1, page_size: int = 12
    ) -> DryRunResult:
        return await self.collect_page(source, page=page, page_size=page_size)

    async def collect_page(
        self, source: SourceCode, *, page: int = 1, page_size: int = 12
    ) -> DryRunResult:
        parser_errors: list[str] = []
        network_errors: list[str] = []
        initial_requests = Counter(self.client.request_counts)

        try:
            list_html = await self.client.fetch_list(source, page=page, page_size=page_size)
        except UlsanMoaNetworkError as exc:
            network_errors.append(f"list: {exc}")
            return self._empty_result(
                source, page, parser_errors, network_errors, initial_requests
            )
        try:
            list_items = parse_list(list_html)
        except UlsanMoaParseError as exc:
            parser_errors.append(f"list: {exc}")
            return self._empty_result(
                source, page, parser_errors, network_errors, initial_requests
            )

        events: list[NormalizedEvent] = []
        detail_success = 0
        detail_failure = 0

        for item in list_items:
            detail: ParsedDetail | None = None
            occurrences: list[ParsedOccurrence] = []

            if not item.is_external:
                try:
                    detail_html = await self.client.fetch_detail(item.detail_url)
                    detail = parse_detail(detail_html, source_url=item.detail_url)
                    detail_success += 1
                except UlsanMoaNetworkError as exc:
                    detail_failure += 1
                    network_errors.append(self._issue("detail", item, exc))
                except UlsanMoaParseError as exc:
                    detail_failure += 1
                    parser_errors.append(self._issue("detail", item, exc))

                if detail is not None and detail.resource_kind in {"EXP", "DAY"}:
                    occurrences.extend(
                        await self._fetch_occurrences(
                            item,
                            detail,
                            parser_errors=parser_errors,
                            network_errors=network_errors,
                        )
                    )

            events.append(normalize_event(source, item, detail, tuple(occurrences)))

        kinds = Counter(item.resource_kind for item in list_items)
        internal_count = len(list_items) - kinds["external"]
        request_counts = self._request_delta(initial_requests)
        samples = tuple(_sample_dict(event) for event in _representative_events(events, 3))
        summary = DryRunSummary(
            source=source,
            page=page,
            list_count=len(list_items),
            internal_count=internal_count,
            external_count=kinds["external"],
            lec_count=kinds["LEC"],
            exp_count=kinds["EXP"],
            day_count=kinds["DAY"],
            detail_success_count=detail_success,
            detail_failure_count=detail_failure,
            occurrence_count=sum(len(event.occurrences) for event in events),
            parser_errors=tuple(parser_errors),
            network_errors=tuple(network_errors),
            request_counts=request_counts,
            samples=samples,
        )
        return DryRunResult(summary=summary, events=tuple(events))

    async def _fetch_occurrences(
        self,
        item: ParsedListItem,
        detail: ParsedDetail,
        *,
        parser_errors: list[str],
        network_errors: list[str],
    ) -> list[ParsedOccurrence]:
        result: list[ParsedOccurrence] = []
        mnu_code = _menu_code(item.detail_url, detail.resource_kind)
        for active_date in detail.active_dates:
            try:
                if detail.resource_kind == "EXP":
                    payload = await self.client.fetch_exp_slots(
                        rsrc_unq_id=detail.source_event_id,
                        rsrc_ymd=active_date,
                        mnu_code=mnu_code,
                    )
                    result.extend(
                        parse_exp_slots(
                            payload,
                            rsrc_unq_id=detail.source_event_id,
                            rsrc_ymd=active_date,
                        )
                    )
                else:
                    payload = await self.client.fetch_day_slots(
                        rsrc_unq_id=detail.source_event_id,
                        rsrc_ymd=active_date,
                        mnu_code=mnu_code,
                    )
                    result.extend(
                        parse_day_slots(
                            payload,
                            rsrc_unq_id=detail.source_event_id,
                            rsrc_ymd=active_date,
                        )
                    )
            except UlsanMoaNetworkError as exc:
                network_errors.append(
                    self._issue(f"slots[{active_date.isoformat()}]", item, exc)
                )
            except UlsanMoaParseError as exc:
                parser_errors.append(
                    self._issue(f"slots[{active_date.isoformat()}]", item, exc)
                )
        return result

    def _empty_result(
        self,
        source: SourceCode,
        page: int,
        parser_errors: list[str],
        network_errors: list[str],
        initial_requests: Counter[str],
    ) -> DryRunResult:
        summary = DryRunSummary(
            source=source,
            page=page,
            list_count=0,
            internal_count=0,
            external_count=0,
            lec_count=0,
            exp_count=0,
            day_count=0,
            detail_success_count=0,
            detail_failure_count=0,
            occurrence_count=0,
            parser_errors=tuple(parser_errors),
            network_errors=tuple(network_errors),
            request_counts=self._request_delta(initial_requests),
            samples=(),
        )
        return DryRunResult(summary=summary, events=())

    def _request_delta(self, initial: Counter[str]) -> dict[str, int]:
        current = Counter(self.client.request_counts)
        keys = (current | initial).keys()
        return {key: current[key] - initial[key] for key in sorted(keys)}

    @staticmethod
    def _issue(phase: str, item: ParsedListItem, exc: Exception) -> str:
        identifier = item.source_event_id or item.detail_url
        return f"{phase} {identifier}: {exc}"


def normalize_event(
    source: SourceCode,
    item: ParsedListItem,
    detail: ParsedDetail | None,
    occurrences: tuple[ParsedOccurrence, ...] = (),
) -> NormalizedEvent:
    """Map parser DTOs to Event-shaped data without inventing timestamps or IDs."""
    source_item_key = build_source_item_key(item.source_event_id, item.detail_url)
    if detail is None:
        return NormalizedEvent(
            source_code=source,
            resource_kind=item.resource_kind,
            title=item.title,
            description=None,
            organizer=item.organizer,
            venue=item.venue,
            address=None,
            original_category=item.original_category,
            target_text=None,
            event_start=None,
            event_end=None,
            event_start_date=item.event_start,
            event_end_date=item.event_end,
            registration_start=None,
            registration_end=None,
            registration_start_date=item.registration_start,
            registration_end_date=item.registration_end,
            registration_period_text=item.registration_period_text,
            event_period_text=item.event_period_text,
            registration_status=item.registration_status_text,
            application_method=item.application_method_text,
            capacity=item.capacity,
            capacity_text=item.capacity_text,
            fee=None,
            fee_text=item.fee_text,
            is_free=item.is_free,
            reservation_url=item.reservation_url,
            detail_url=item.detail_url,
            image_url=item.image_url,
            source_event_id=item.source_event_id,
            source_item_key=source_item_key,
            source_url=item.detail_url,
            occurrences=occurrences,
        )

    return NormalizedEvent(
        source_code=source,
        resource_kind=detail.resource_kind,
        title=detail.title,
        description=detail.description,
        organizer=detail.organizer,
        venue=detail.venue,
        address=detail.address,
        original_category=item.original_category,
        target_text=detail.target_text,
        event_start=detail.event_start,
        event_end=detail.event_end,
        event_start_date=None if detail.event_start is not None else item.event_start,
        event_end_date=None if detail.event_end is not None else item.event_end,
        registration_start=detail.registration_start,
        registration_end=detail.registration_end,
        registration_start_date=(
            None if detail.registration_start is not None else item.registration_start
        ),
        registration_end_date=(
            None if detail.registration_end is not None else item.registration_end
        ),
        registration_period_text=detail.registration_period_text,
        event_period_text=detail.event_period_text,
        registration_status=item.registration_status_text,
        application_method=detail.application_method_text,
        capacity=detail.capacity,
        capacity_text=detail.capacity_text,
        fee=Decimal("0") if detail.is_free is True else None,
        fee_text=detail.fee_text,
        is_free=detail.is_free,
        reservation_url=detail.reservation_url,
        detail_url=detail.detail_url,
        image_url=detail.image_url or item.image_url,
        source_event_id=detail.source_event_id,
        source_item_key=build_source_item_key(detail.source_event_id, detail.detail_url),
        source_url=detail.detail_url,
        occurrences=occurrences,
    )


def build_source_item_key(source_event_id: str | None, source_url: str) -> str:
    """Build the stable per-Source key without inventing an official source ID."""
    if source_event_id is not None:
        return source_event_id
    canonical_url = canonicalize_url(source_url)
    digest = sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"urlsha256:{digest}"


def _menu_code(url: str, resource_kind: str) -> str:
    values = parse_qs(urlsplit(url).query).get("mnu_code", [])
    if len(values) == 1:
        return values[0]
    return "F401" if resource_kind == "EXP" else "F601"


def _representative_events(
    events: list[NormalizedEvent], limit: int
) -> list[NormalizedEvent]:
    selected: list[NormalizedEvent] = []
    seen_kinds: set[str] = set()
    for event in events:
        if event.resource_kind not in seen_kinds:
            selected.append(event)
            seen_kinds.add(event.resource_kind)
        if len(selected) == limit:
            return selected
    for event in events:
        if event not in selected:
            selected.append(event)
        if len(selected) == limit:
            break
    return selected


def _sample_dict(event: NormalizedEvent) -> dict[str, object]:
    value = asdict(event)
    value.pop("description", None)
    occurrences = cast(list[dict[str, object]], value.pop("occurrences"))
    value["occurrence_count"] = len(occurrences)
    value["occurrence_samples"] = occurrences[:2]
    return value

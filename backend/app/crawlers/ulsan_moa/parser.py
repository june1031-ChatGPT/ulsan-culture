from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Sequence
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from app.crawlers.ulsan_moa.config import ULSAN_MOA_SOURCE

BASE_URL = ULSAN_MOA_SOURCE.host_url
SEOUL = ZoneInfo("Asia/Seoul")
ResourceKind = Literal["LEC", "EXP", "DAY", "external"]

_RESOURCE_ID_PATTERN = re.compile(r"^(LEC|EXP|DAY)_[A-Za-z0-9_]+$")
_JSESSION_PATTERN = re.compile(r";jsessionid=[^/?#&;]*", re.IGNORECASE)
_DATE_RANGE_PATTERN = re.compile(
    r"(?P<start>\d{4}-\d{2}-\d{2})\s*~\s*(?P<end>\d{4}-\d{2}-\d{2})"
)
_DATETIME_RANGE_PATTERN = re.compile(
    r"(?P<start>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})"
    r"\s*~\s*"
    r"(?P<end>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})"
)
_TARGET_KEYWORDS = (
    "대상",
    "연령",
    "유아",
    "어린이",
    "초등",
    "중학생",
    "고등학생",
    "청소년",
    "성인",
    "가족",
    "보호자",
)


class UlsanMoaParseError(ValueError):
    """Raised when an expected Ulsan Moa response shape is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ParsedListItem:
    title: str
    organizer: str | None
    venue: str | None
    source_event_id: str | None
    resource_kind: ResourceKind
    is_external: bool
    detail_url: str
    reservation_url: str
    image_url: str | None
    registration_start: date | None
    registration_end: date | None
    registration_period_text: str | None
    event_start: date | None
    event_end: date | None
    event_period_text: str | None
    capacity: int | None
    capacity_text: str | None
    fee_text: str | None
    is_free: bool | None
    registration_status_text: str | None
    application_method_text: str | None
    original_category: str | None


@dataclass(frozen=True, slots=True)
class ParsedDetail:
    resource_kind: Literal["LEC", "EXP", "DAY"]
    source_event_id: str
    title: str
    organizer: str | None
    venue: str | None
    address: str | None
    target_summary: str | None
    target_detail_text: str | None
    target_text: str | None
    description: str | None
    registration_start: datetime | None
    registration_end: datetime | None
    registration_period_text: str | None
    event_start: datetime | None
    event_end: datetime | None
    event_period_text: str | None
    capacity: int | None
    reserved_count: int | None
    capacity_text: str | None
    fee_text: str | None
    is_free: bool | None
    application_method_text: str | None
    detail_url: str
    reservation_url: str
    image_url: str | None
    active_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class ParsedOccurrence:
    start_at: datetime
    end_at: datetime
    source_occurrence_id: str
    capacity: int | None
    reserved_count: int | None
    available_count: int | None
    fee: Decimal | None
    is_free: bool | None
    application_available: bool | None
    source_raw_data: dict[str, Any]


def canonicalize_url(url: str, *, base_url: str = BASE_URL) -> str:
    """Return an absolute URL without transient session path parameters or fragments."""
    absolute = urljoin(base_url, url.strip())
    parts = urlsplit(absolute)
    path = _JSESSION_PATTERN.sub("", parts.path)
    hostname = (parts.hostname or "").lower()
    scheme = parts.scheme.lower()
    netloc = parts.netloc

    if hostname in {"ulsan.go.kr", "www.ulsan.go.kr"}:
        scheme = "https"
        netloc = "ulsan.go.kr"
        if parts.port and parts.port != 443:
            netloc = f"{netloc}:{parts.port}"

    return urlunsplit((scheme, netloc, path, parts.query, ""))


def parse_list(html: str, *, base_url: str = BASE_URL) -> list[ParsedListItem]:
    """Parse an F300 or F400 gallery page without performing network requests."""
    soup = _soup(html)
    board = soup.select_one("ul.img-board")
    if board is None:
        raise UlsanMoaParseError("list response is missing ul.img-board")

    cards = board.find_all("li", recursive=False)
    if not cards:
        raise UlsanMoaParseError("list response contains no direct card items")

    return [_parse_list_card(card, base_url=base_url) for card in cards]


def parse_detail(html: str, *, source_url: str) -> ParsedDetail:
    """Dispatch only Ulsan Moa internal detail URLs to the matching parser."""
    canonical_url = canonicalize_url(source_url)
    resource_kind, _ = _resource_from_url(canonical_url)
    if resource_kind == "external":
        raise UlsanMoaParseError("external linked events do not use Ulsan Moa detail parsers")
    if resource_kind == "LEC":
        return parse_lec_detail(html, source_url=canonical_url)
    if resource_kind == "EXP":
        return parse_exp_detail(html, source_url=canonical_url)
    return parse_day_detail(html, source_url=canonical_url)


def parse_lec_detail(html: str, *, source_url: str | None = None) -> ParsedDetail:
    return _parse_internal_detail(html, expected_kind="LEC", source_url=source_url)


def parse_exp_detail(html: str, *, source_url: str | None = None) -> ParsedDetail:
    return _parse_internal_detail(html, expected_kind="EXP", source_url=source_url)


def parse_day_detail(html: str, *, source_url: str | None = None) -> ParsedDetail:
    return _parse_internal_detail(html, expected_kind="DAY", source_url=source_url)


def parse_exp_slots(
    payload: str | bytes | Sequence[dict[str, Any]],
    *,
    rsrc_unq_id: str,
    rsrc_ymd: str | date,
) -> list[ParsedOccurrence]:
    _require_resource_id(rsrc_unq_id, "EXP")
    occurrence_date = _coerce_date(rsrc_ymd)
    rows = _load_slot_rows(payload)
    parsed: list[ParsedOccurrence] = []

    for index, row in enumerate(rows):
        oprt_id = _required_int(row, "oprtId", index=index)
        start_at, end_at = _slot_datetimes(row, occurrence_date, index=index)
        capacity = _optional_nonnegative_int(row, "useLmtNmpr", index=index)
        reserved = _optional_nonnegative_int(row, "rsvCnt", index=index)
        available = _available_count(capacity, reserved, index=index)
        fee = _optional_decimal(row.get("fee"), field="fee", index=index)

        parsed.append(
            ParsedOccurrence(
                start_at=start_at,
                end_at=end_at,
                source_occurrence_id=f"{rsrc_unq_id}:{occurrence_date.isoformat()}:{oprt_id}",
                capacity=capacity,
                reserved_count=reserved,
                available_count=available,
                fee=fee,
                is_free=(fee == 0) if fee is not None else None,
                application_available=_application_available(row.get("aplyYn")),
                source_raw_data=deepcopy(row),
            )
        )
    return parsed


def parse_day_slots(
    payload: str | bytes | Sequence[dict[str, Any]],
    *,
    rsrc_unq_id: str,
    rsrc_ymd: str | date,
) -> list[ParsedOccurrence]:
    _require_resource_id(rsrc_unq_id, "DAY")
    occurrence_date = _coerce_date(rsrc_ymd)
    rows = _load_slot_rows(payload)
    parsed: list[ParsedOccurrence] = []

    for index, row in enumerate(rows):
        start_at, end_at = _slot_datetimes(row, occurrence_date, index=index)
        capacity = _optional_nonnegative_int(row, "lmtNmpr", index=index)
        reserved = _optional_nonnegative_int(row, "curNope", index=index)
        available = _available_count(capacity, reserved, index=index)
        fee = _optional_decimal(row.get("fee"), field="fee", index=index)
        start_text = start_at.strftime("%H:%M")
        end_text = end_at.strftime("%H:%M")

        parsed.append(
            ParsedOccurrence(
                start_at=start_at,
                end_at=end_at,
                source_occurrence_id=(
                    f"{rsrc_unq_id}:{occurrence_date.isoformat()}:{start_text}:{end_text}"
                ),
                capacity=capacity,
                reserved_count=reserved,
                available_count=available,
                fee=fee,
                is_free=(fee == 0) if fee is not None else None,
                application_available=_application_available(row.get("aplyYn")),
                source_raw_data=deepcopy(row),
            )
        )
    return parsed


def _parse_list_card(card: Tag, *, base_url: str) -> ParsedListItem:
    link = card.find("a", href=True)
    title_node = card.select_one(".con-box h4.tit")
    if link is None or title_node is None:
        raise UlsanMoaParseError("list card is missing its link or title")

    title = _text(title_node)
    if not title:
        raise UlsanMoaParseError("list card title is empty")

    detail_url = canonicalize_url(str(link["href"]), base_url=base_url)
    resource_kind, source_event_id = _resource_from_url(detail_url)
    fields = _label_values(card.select(".con-box ul.info > li"))
    registration_text = fields.get("접수기간")
    event_text = fields.get("강좌기간")
    registration_start, registration_end = _parse_date_range(registration_text)
    event_start, event_end = _parse_date_range(event_text)
    capacity_text = fields.get("모집정원")

    image = card.select_one(".thumb img[src]")
    image_url = (
        canonicalize_url(str(image["src"]), base_url=base_url) if image is not None else None
    )
    place = _optional_text(card.select_one(".con-box p.place"))
    fee_text = fields.get("이용료") or _optional_text(card.select_one(".thumb .bd-label.type3"))
    if not fee_text:
        fee_text = _optional_text(card.select_one(".thumb .bd-label.type4"))

    return ParsedListItem(
        title=title,
        organizer=place,
        venue=fields.get("장소") or place,
        source_event_id=source_event_id,
        resource_kind=resource_kind,
        is_external=resource_kind == "external",
        detail_url=detail_url,
        reservation_url=detail_url,
        image_url=image_url,
        registration_start=registration_start,
        registration_end=registration_end,
        registration_period_text=registration_text,
        event_start=event_start,
        event_end=event_end,
        event_period_text=event_text,
        capacity=_plain_integer(capacity_text),
        capacity_text=capacity_text,
        fee_text=fee_text,
        is_free=_free_value(fee_text),
        registration_status_text=_optional_text(card.select_one(".thumb .bd-label.type1")),
        application_method_text=_optional_text(card.select_one(".thumb .ico-wrap .ico")),
        original_category=fields.get("시설종류") or fields.get("분류"),
    )


def _parse_internal_detail(
    html: str,
    *,
    expected_kind: Literal["LEC", "EXP", "DAY"],
    source_url: str | None,
) -> ParsedDetail:
    soup = _soup(html)
    view_info = soup.select_one(".reserve-view .view-info")
    if view_info is None:
        raise UlsanMoaParseError("detail response is missing .reserve-view .view-info")

    resource_input = soup.select_one('input[name="rsrcUnqId"][value]')
    if resource_input is None:
        raise UlsanMoaParseError("detail response is missing rsrcUnqId")
    source_event_id = str(resource_input["value"]).strip()
    _require_resource_id(source_event_id, expected_kind)

    title = _detail_title(view_info)
    if not title:
        raise UlsanMoaParseError("detail response title is empty")
    organizer = _optional_text(view_info.select_one(".info-box .top .place"))
    fields = _summary_fields(view_info)
    target_summary = _clean_target_summary(fields.get("대상"))
    panel = soup.select_one("#panel-1")
    description = _optional_text(panel, separator="\n")
    target_detail = _extract_target_detail_text(description)
    target_text = _join_distinct(target_summary, target_detail)

    registration_text = fields.get("접수기간")
    registration_start, registration_end = _parse_datetime_range(registration_text)
    event_text = fields.get("강좌기간") if expected_kind == "LEC" else None
    event_start, event_end = _parse_datetime_range(event_text)
    if expected_kind != "LEC" and (event_start is not None or event_end is not None):
        raise UlsanMoaParseError("EXP/DAY detail must not create event times from registration data")

    capacity = None
    reserved_count = None
    capacity_text = fields.get("접수현황")
    if expected_kind == "LEC" and capacity_text:
        status_match = re.search(r"(?P<reserved>\d+)\s*/\s*(?P<capacity>\d+)", capacity_text)
        if status_match:
            reserved_count = int(status_match.group("reserved"))
            capacity = int(status_match.group("capacity"))

    inferred_url = source_url or _detail_url_from_html(soup, source_event_id, expected_kind)
    detail_url = canonicalize_url(inferred_url)
    url_kind, url_id = _resource_from_url(detail_url)
    if url_kind != expected_kind or url_id != source_event_id:
        raise UlsanMoaParseError("detail URL and HTML resource ID do not match")

    image = view_info.select_one(".img-wrap img[src]")
    image_url = canonicalize_url(str(image["src"])) if image is not None else None
    fee_text = fields.get("요금") or fields.get("이용요금")

    return ParsedDetail(
        resource_kind=expected_kind,
        source_event_id=source_event_id,
        title=title,
        organizer=organizer,
        venue=fields.get("장소명") or organizer,
        address=_detail_address(soup) or fields.get("장소"),
        target_summary=target_summary,
        target_detail_text=target_detail,
        target_text=target_text,
        description=description,
        registration_start=registration_start,
        registration_end=registration_end,
        registration_period_text=registration_text,
        event_start=event_start,
        event_end=event_end,
        event_period_text=event_text,
        capacity=capacity,
        reserved_count=reserved_count,
        capacity_text=capacity_text,
        fee_text=fee_text,
        is_free=_free_value(fee_text),
        application_method_text=fields.get("예약방법"),
        detail_url=detail_url,
        reservation_url=detail_url,
        image_url=image_url,
        active_dates=_active_dates(soup) if expected_kind in {"EXP", "DAY"} else (),
    )


def _soup(html: str) -> BeautifulSoup:
    if not isinstance(html, str) or not html.strip():
        raise UlsanMoaParseError("HTML response is empty")
    return BeautifulSoup(html, "lxml")


def _resource_from_url(url: str) -> tuple[ResourceKind, str | None]:
    parts = urlsplit(url)
    values = parse_qs(parts.query).get("rsrcUnqId", [])
    if len(values) != 1:
        return "external", None
    source_event_id = values[0]
    match = _RESOURCE_ID_PATTERN.fullmatch(source_event_id)
    if not match or (parts.hostname or "").lower() not in {"ulsan.go.kr", "www.ulsan.go.kr"}:
        return "external", None
    return match.group(1), source_event_id  # type: ignore[return-value]


def _require_resource_id(source_event_id: str, expected_kind: str) -> None:
    match = _RESOURCE_ID_PATTERN.fullmatch(source_event_id)
    if not match or match.group(1) != expected_kind:
        raise UlsanMoaParseError(
            f"expected {expected_kind} resource ID, received {source_event_id!r}"
        )


def _summary_fields(view_info: Tag) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in view_info.select(".info-box ul.cont > li"):
        label_node = item.select_one("span.tit")
        value_node = item.find("p")
        label = _optional_text(label_node)
        value = _optional_text(value_node)
        if label and value:
            fields[label] = value
    if not fields:
        raise UlsanMoaParseError("detail response has no summary fields")
    return fields


def _detail_title(view_info: Tag) -> str | None:
    title_node = view_info.select_one(".info-box .top .tit")
    title = _optional_text(title_node)
    if title or title_node is None:
        return title

    # The live page nests a <p> inside <h4>, which lxml correctly repairs into
    # a following sibling. Keep this narrow fallback so a broader DOM change fails.
    sibling = title_node.find_next_sibling("p")
    return _optional_text(sibling)


def _label_values(nodes: Sequence[Tag]) -> dict[str, str]:
    values: dict[str, str] = {}
    for node in nodes:
        text = _text(node)
        if ":" not in text:
            continue
        label, value = text.split(":", 1)
        if label.strip() and value.strip():
            values[label.strip()] = value.strip()
    return values


def _parse_date_range(value: str | None) -> tuple[date | None, date | None]:
    if not value or "상시" in value:
        return None, None
    match = _DATE_RANGE_PATTERN.search(value)
    if not match:
        return None, None
    return date.fromisoformat(match.group("start")), date.fromisoformat(match.group("end"))


def _parse_datetime_range(value: str | None) -> tuple[datetime | None, datetime | None]:
    if not value or "상시" in value:
        return None, None
    match = _DATETIME_RANGE_PATTERN.search(value)
    if not match:
        return None, None
    start = datetime.strptime(match.group("start"), "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL)
    end = datetime.strptime(match.group("end"), "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL)
    if end < start:
        raise UlsanMoaParseError("parsed period ends before it starts")
    return start, end


def _active_dates(soup: BeautifulSoup) -> tuple[date, ...]:
    result: list[date] = []
    for button in soup.select('#view_calendar button[data-date]:not([disabled])'):
        value = str(button.get("data-date", "")).strip()
        if value:
            result.append(_coerce_date(value))
    return tuple(dict.fromkeys(result))


def _detail_address(soup: BeautifulSoup) -> str | None:
    panel = soup.select_one("#panel-3")
    if panel is None:
        return None
    for heading in panel.find_all(["h3", "h4", "strong"]):
        if _text(heading) != "주소":
            continue
        value = heading.find_next_sibling("p")
        return _optional_text(value)
    return None


def _detail_url_from_html(
    soup: BeautifulSoup, source_event_id: str, kind: Literal["LEC", "EXP", "DAY"]
) -> str:
    menu_code: str | None = None
    form = soup.select_one("form[action*='mnu_code=']")
    if form is not None:
        action = str(form.get("action", ""))
        menu_values = parse_qs(urlsplit(urljoin(BASE_URL, action)).query).get("mnu_code", [])
        if menu_values:
            menu_code = menu_values[0]
    if not menu_code:
        menu_code = {"EXP": "F401", "DAY": "F601"}.get(kind)
    if not menu_code:
        raise UlsanMoaParseError("LEC detail source_url or menu code is required")
    return (
        f"{BASE_URL}/y/yes/page.do?mnu_code={menu_code}"
        f"&step=step01&rsrcUnqId={source_event_id}"
    )


def _extract_target_detail_text(description: str | None) -> str | None:
    if not description:
        return None
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    selected: list[str] = []
    in_target_section = False
    for line in lines:
        compact = line.lstrip("▷●○-*※★ ")
        is_section = compact.startswith("■") or line.startswith("■")
        if is_section:
            in_target_section = "대상" in line or "참여 기준" in line or "참가 기준" in line
            if in_target_section:
                selected.append(line)
            continue
        if in_target_section or any(keyword in line for keyword in _TARGET_KEYWORDS):
            selected.append(line)
    return _join_unique_lines(selected)


def _clean_target_summary(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s*만 나이 기준\s*$", "", value).strip()
    return cleaned or None


def _load_slot_rows(
    payload: str | bytes | Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    if isinstance(payload, str):
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise UlsanMoaParseError("slot response is not valid JSON") from exc
    else:
        value = payload
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise UlsanMoaParseError("slot response root must be a JSON array")
    rows = list(value)
    if not all(isinstance(row, dict) for row in rows):
        raise UlsanMoaParseError("every slot row must be a JSON object")
    return rows


def _slot_datetimes(
    row: dict[str, Any], occurrence_date: date, *, index: int
) -> tuple[datetime, datetime]:
    start_text = _required_time(row, "stTm", index=index)
    end_text = _required_time(row, "enTm", index=index)
    start_at = datetime.combine(occurrence_date, start_text, tzinfo=SEOUL)
    end_at = datetime.combine(occurrence_date, end_text, tzinfo=SEOUL)
    if end_at < start_at:
        raise UlsanMoaParseError(f"slot row {index} ends before it starts")
    return start_at, end_at


def _required_time(row: dict[str, Any], field: str, *, index: int):
    value = row.get(field)
    if not isinstance(value, str):
        raise UlsanMoaParseError(f"slot row {index} has no string {field}")
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise UlsanMoaParseError(f"slot row {index} has invalid {field}") from exc


def _required_int(row: dict[str, Any], field: str, *, index: int) -> int:
    value = _optional_nonnegative_int(row, field, index=index)
    if value is None:
        raise UlsanMoaParseError(f"slot row {index} has no {field}")
    return value


def _optional_nonnegative_int(
    row: dict[str, Any], field: str, *, index: int
) -> int | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UlsanMoaParseError(f"slot row {index} has invalid {field}")
    return value


def _optional_decimal(value: Any, *, field: str, index: int) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise UlsanMoaParseError(f"slot row {index} has invalid {field}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise UlsanMoaParseError(f"slot row {index} has invalid {field}") from exc
    if parsed < 0:
        raise UlsanMoaParseError(f"slot row {index} has negative {field}")
    return parsed


def _available_count(capacity: int | None, reserved: int | None, *, index: int) -> int | None:
    if capacity is None or reserved is None:
        return None
    if reserved > capacity:
        raise UlsanMoaParseError(f"slot row {index} reserved count exceeds capacity")
    return capacity - reserved


def _application_available(value: Any) -> bool | None:
    if value == "Y":
        return True
    if value == "N":
        return False
    if value is None or value == "":
        return None
    raise UlsanMoaParseError(f"unknown aplyYn value: {value!r}")


def _coerce_date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise UlsanMoaParseError(f"invalid occurrence date: {value!r}") from exc


def _plain_integer(value: str | None) -> int | None:
    if not value or not re.fullmatch(r"\d+", value.strip()):
        return None
    return int(value)


def _free_value(value: str | None) -> bool | None:
    if not value:
        return None
    compact = re.sub(r"\s+", "", value)
    if compact == "무료":
        return True
    if compact == "유료":
        return False
    return None


def _join_distinct(*values: str | None) -> str | None:
    return _join_unique_lines(value for value in values if value)


def _join_unique_lines(values) -> str | None:
    unique: list[str] = []
    for value in values:
        normalized = re.sub(r"[^\S\n]+", " ", str(value)).strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return "\n".join(unique) or None


def _text(node: Tag, *, separator: str = " ") -> str:
    return re.sub(r"[^\S\n]+", " ", node.get_text(separator, strip=True)).strip()


def _optional_text(node: Tag | None, *, separator: str = " ") -> str | None:
    if node is None:
        return None
    value = _text(node, separator=separator)
    return value or None

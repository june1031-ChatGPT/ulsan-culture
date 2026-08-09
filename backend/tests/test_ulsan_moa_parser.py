from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from app.crawlers.ulsan_moa import (
    UlsanMoaParseError,
    build_source_item_key,
    canonicalize_url,
    normalize_event,
    parse_day_detail,
    parse_day_slots,
    parse_detail,
    parse_exp_detail,
    parse_exp_slots,
    parse_lec_detail,
    parse_list,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ulsan_moa"
LEC_URL = (
    "https://ulsan.go.kr/y/yes/page.do?mnu_code=F303&step=step01"
    "&rsrcUnqId=LEC_0000000000000828"
)
EXP_URL = (
    "https://ulsan.go.kr/y/yes/page.do?mnu_code=F401&step=step01"
    "&rsrcUnqId=EXP_0000000000000050"
)
DAY_URL = (
    "https://ulsan.go.kr/y/yes/page.do?mnu_code=F601&step=step01"
    "&rsrcUnqId=DAY_0000000000000000"
)


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_fixtures_have_no_real_session_identifier():
    for path in FIXTURE_DIR.iterdir():
        if path.suffix not in {".html", ".json"}:
            continue
        assert ";jsessionid=" not in path.read_text(encoding="utf-8").lower()


def test_parse_f300_list_extracts_internal_and_external_cards_without_invented_times():
    items = parse_list(fixture_text("f300_list.html"))

    assert len(items) == 12
    internal = next(item for item in items if item.source_event_id == "LEC_0000000000000828")
    assert internal.title == "과학으로 배우는 문화유산 (유물 복원 체험) - 8월 13일(목)"
    assert internal.organizer == "울산대곡박물관"
    assert internal.venue == "울산대곡박물관"
    assert internal.resource_kind == "LEC"
    assert internal.is_external is False
    assert internal.detail_url == LEC_URL
    assert internal.registration_start == date(2026, 7, 1)
    assert internal.registration_end == date(2026, 8, 10)
    assert internal.event_start == date(2026, 8, 13)
    assert internal.event_end == date(2026, 8, 13)
    assert not isinstance(internal.registration_start, datetime)
    assert not isinstance(internal.event_end, datetime)
    assert internal.capacity == 20
    assert internal.capacity_text == "20"

    external = items[0]
    assert external.title == "[3분기]매일이 새로운 집밥클래스(8월)(3회)"
    assert external.organizer == "평생학습관"
    assert external.resource_kind == "external"
    assert external.source_event_id is None
    assert external.is_external is True
    assert external.detail_url.startswith("https://crs.ubimc.or.kr/")


def test_parse_f400_list_extracts_exp_card_and_keeps_external_links_external():
    items = parse_list(fixture_text("f400_list.html"))

    assert len(items) == 12
    internal = next(item for item in items if item.source_event_id == "EXP_0000000000000050")
    assert internal.title == "가족 아트워크숍"
    assert internal.organizer == "울산시립미술관"
    assert internal.venue == "울산시립미술관"
    assert internal.resource_kind == "EXP"
    assert internal.detail_url == EXP_URL
    assert internal.registration_start == date(2026, 8, 3)
    assert internal.registration_end == date(2026, 8, 10)
    assert internal.event_start is None
    assert internal.event_end is None

    external = items[0]
    assert external.title == "(자막)모아나"
    assert external.organizer == "HD아트센터"
    assert external.venue == "HD아트센터"
    assert external.resource_kind == "external"
    assert external.source_event_id is None
    assert external.detail_url.startswith("https://hd-artscenter.co.kr/")


def test_canonical_url_removes_jsessionid_and_normalizes_ulsan_host():
    dirty = (
        "http://www.ulsan.go.kr/y/yes/page.do;jsessionid=SECRET123"
        "?mnu_code=F601&step=step01&rsrcUnqId=DAY_0000000000000000#calendar"
    )

    assert canonicalize_url(dirty) == DAY_URL


def test_detail_dispatch_rejects_external_link_before_internal_html_parsing():
    with pytest.raises(UlsanMoaParseError, match="external linked events"):
        parse_detail("<html></html>", source_url="https://example.org/event/1")


def test_parse_lec_detail_separates_registration_and_event_periods():
    detail = parse_lec_detail(fixture_text("lec_detail.html"), source_url=LEC_URL)

    assert detail.resource_kind == "LEC"
    assert detail.source_event_id == "LEC_0000000000000828"
    assert detail.title == "과학으로 배우는 문화유산 (유물 복원 체험) - 8월 13일(목)"
    assert detail.organizer == "울산대곡박물관"
    assert detail.venue == "울산대곡박물관"
    assert detail.address is None
    assert detail.registration_start.isoformat() == "2026-07-01T09:00:00+09:00"
    assert detail.registration_end.isoformat() == "2026-08-10T17:00:00+09:00"
    assert detail.event_start.isoformat() == "2026-08-13T10:30:00+09:00"
    assert detail.event_end.isoformat() == "2026-08-13T12:00:00+09:00"
    assert detail.capacity == 20
    assert detail.reserved_count == 12
    assert detail.target_summary == "제한없음"
    assert "6세 이상" in detail.target_text
    assert "초등학생 개인 및 단체" in detail.target_text
    assert detail.active_dates == ()
    assert detail.detail_url == detail.reservation_url == LEC_URL


def test_normalize_exact_datetime_event_uses_only_datetime_fields_and_internal_key():
    item = next(
        item
        for item in parse_list(fixture_text("f300_list.html"))
        if item.source_event_id == "LEC_0000000000000828"
    )
    detail = parse_lec_detail(fixture_text("lec_detail.html"), source_url=LEC_URL)

    event = normalize_event("F300", item, detail)

    assert event.event_start == detail.event_start
    assert event.event_end == detail.event_end
    assert event.registration_start == detail.registration_start
    assert event.registration_end == detail.registration_end
    assert event.event_start_date is None
    assert event.event_end_date is None
    assert event.registration_start_date is None
    assert event.registration_end_date is None
    assert event.source_event_id == "LEC_0000000000000828"
    assert event.source_item_key == event.source_event_id


def test_normalize_date_only_external_event_uses_canonical_url_hash_key():
    item = parse_list(fixture_text("f300_list.html"))[0]

    event = normalize_event("F300", item, None)
    expected = sha256(canonicalize_url(item.detail_url).encode("utf-8")).hexdigest()

    assert event.event_start is None
    assert event.event_end is None
    assert event.registration_start is None
    assert event.registration_end is None
    assert event.event_start_date == item.event_start
    assert event.event_end_date == item.event_end
    assert event.registration_start_date == item.registration_start
    assert event.registration_end_date == item.registration_end
    assert event.source_event_id is None
    assert event.source_item_key == f"urlsha256:{expected}"
    assert build_source_item_key(None, f"{item.detail_url}#temporary") == event.source_item_key


def test_parse_exp_detail_preserves_specific_target_constraints_and_active_dates():
    detail = parse_exp_detail(fixture_text("exp_detail.html"), source_url=EXP_URL)

    assert detail.resource_kind == "EXP"
    assert detail.title == "가족 아트워크숍"
    assert detail.organizer == "울산시립미술관"
    assert detail.venue == "울산시립미술관"
    assert detail.address == "울산 중구 미술관길 72울산시립미술관"
    assert detail.registration_start.isoformat() == "2026-08-03T10:00:00+09:00"
    assert detail.registration_end.isoformat() == "2026-08-10T17:00:00+09:00"
    assert detail.event_start is None
    assert detail.event_end is None
    assert detail.target_summary == "단체"
    assert "6세 이상 어린이를 포함한 가족 10팀" in detail.target_text
    assert "가족당 최대 4명 참여" in detail.target_text
    assert detail.capacity is None
    assert detail.capacity_text is None
    assert detail.active_dates == (
        date(2026, 8, 11),
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 17),
        date(2026, 8, 19),
    )


def test_parse_day_detail_preserves_always_open_registration_as_text_and_null_dates():
    detail = parse_day_detail(fixture_text("day_detail.html"), source_url=DAY_URL)

    assert detail.resource_kind == "DAY"
    assert detail.source_event_id == "DAY_0000000000000000"
    assert detail.title == "어린이 박물관(이용시간 50분)"
    assert detail.organizer == "울산박물관"
    assert detail.venue == "울산박물관"
    assert detail.registration_period_text == "상시"
    assert detail.registration_start is None
    assert detail.registration_end is None
    assert detail.event_start is None
    assert detail.event_end is None
    assert "초등학생 이하 어린이 및 동반 가족" in detail.target_text
    assert date(2026, 8, 12) in detail.active_dates


def test_parse_exp_slots_builds_stable_ids_and_preserves_unmerged_capacity_constraints():
    payload = fixture_text("exp_time_slots.json")
    occurrences = parse_exp_slots(
        payload,
        rsrc_unq_id="EXP_0000000000000050",
        rsrc_ymd="2026-08-11",
    )

    assert len(occurrences) == 1
    occurrence = occurrences[0]
    assert occurrence.source_occurrence_id == "EXP_0000000000000050:2026-08-11:326"
    assert occurrence.start_at.isoformat() == "2026-08-11T10:00:00+09:00"
    assert occurrence.end_at.isoformat() == "2026-08-11T12:00:00+09:00"
    assert occurrence.capacity == 40
    assert occurrence.reserved_count == 17
    assert occurrence.available_count == 23
    assert occurrence.application_available is True
    assert occurrence.fee is None
    assert occurrence.is_free is None
    assert occurrence.source_raw_data["maxPer"] == 4
    assert occurrence.source_raw_data["useLmtNmpr"] == 40


def test_parse_day_slots_builds_time_based_ids_and_preserves_each_raw_row():
    payload = fixture_text("day_time_slots.json")
    occurrences = parse_day_slots(
        payload,
        rsrc_unq_id="DAY_0000000000000000",
        rsrc_ymd=date(2026, 8, 10),
    )

    assert len(occurrences) == 7
    first = occurrences[0]
    last = occurrences[-1]
    assert first.source_occurrence_id == "DAY_0000000000000000:2026-08-10:09:30:10:30"
    assert last.source_occurrence_id == "DAY_0000000000000000:2026-08-10:16:30:17:30"
    assert first.start_at.isoformat() == "2026-08-10T09:30:00+09:00"
    assert first.end_at.isoformat() == "2026-08-10T10:30:00+09:00"
    assert first.capacity == 50
    assert first.reserved_count == 50
    assert first.available_count == 0
    assert first.application_available is False
    assert first.fee is None
    assert first.is_free is None
    assert first.source_raw_data == {
        "stTm": "09:30",
        "enTm": "10:30",
        "aplyYn": "N",
        "fee": None,
        "lmtNmpr": 50,
        "curNope": 50,
    }


def test_parsers_fail_loudly_for_changed_or_invalid_response_shapes():
    with pytest.raises(UlsanMoaParseError, match="ul.img-board"):
        parse_list("<html><body>TRACER waiting page</body></html>")

    with pytest.raises(UlsanMoaParseError, match="view-info"):
        parse_lec_detail("<html><body>blocked</body></html>", source_url=LEC_URL)

    with pytest.raises(UlsanMoaParseError, match="valid JSON"):
        parse_exp_slots(
            "not-json",
            rsrc_unq_id="EXP_0000000000000050",
            rsrc_ymd="2026-08-11",
        )


def test_slot_parser_does_not_infer_fee_or_capacity_from_unrelated_constraints():
    occurrence = parse_exp_slots(
        '[{"oprtId":1,"stTm":"10:00","enTm":"11:00","aplyYn":"Y",'
        '"useLmtNmpr":null,"maxPer":4,"fee":0}]',
        rsrc_unq_id="EXP_0000000000000099",
        rsrc_ymd="2026-08-20",
    )[0]

    assert occurrence.capacity is None
    assert occurrence.reserved_count is None
    assert occurrence.available_count is None
    assert occurrence.fee == Decimal("0")
    assert occurrence.is_free is True
    assert occurrence.source_raw_data["maxPer"] == 4

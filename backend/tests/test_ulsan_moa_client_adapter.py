import asyncio
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.crawlers.ulsan_moa import (
    UlsanMoaAdapter,
    UlsanMoaClient,
    UlsanMoaNetworkError,
    is_retryable_status,
)
from app.crawlers.ulsan_moa.cli import format_summary


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ulsan_moa"
EXP_URL = (
    "https://ulsan.go.kr/y/yes/page.do?mnu_code=F401&step=step01"
    "&rsrcUnqId=EXP_0000000000000050"
)


def fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_client_builds_only_documented_non_www_urls_and_parameters():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("SelectTimeList.do"):
            return httpx.Response(200, json=[])
        if request.url.params.get("step") == "step01":
            return httpx.Response(
                200,
                text='<div class="reserve-view"><div class="view-info"></div></div>',
            )
        return httpx.Response(200, text='<ul class="img-board"><li></li></ul>')

    async def scenario() -> None:
        async_client = httpx.AsyncClient(
            base_url="https://ulsan.go.kr", transport=httpx.MockTransport(handler)
        )
        client = UlsanMoaClient(http_client=async_client, max_retries=0)
        await client.fetch_list("F300", page=2, page_size=7)
        await client.fetch_list("F400", page=1, page_size=12)
        await client.fetch_detail(
            "http://www.ulsan.go.kr/y/yes/page.do;jsessionid=TEMP"
            "?mnu_code=F401&step=step01&rsrcUnqId=EXP_0000000000000050"
        )
        await client.fetch_exp_slots(
            rsrc_unq_id="EXP_0000000000000050",
            rsrc_ymd=date(2026, 8, 11),
            mnu_code="F401",
        )
        await client.fetch_day_slots(
            rsrc_unq_id="DAY_0000000000000000",
            rsrc_ymd=date(2026, 8, 12),
        )
        await async_client.aclose()

    asyncio.run(scenario())

    assert all(request.url.host == "ulsan.go.kr" for request in requests)
    assert all(";jsessionid" not in request.url.path for request in requests)
    assert dict(requests[0].url.params) == {
        "mnu_code": "F300",
        "step": "gallery",
        "orderBy": "rcept",
        "pageNo": "2",
        "pageSize": "7",
    }
    assert requests[1].url.params["step"] == "list_img"
    assert requests[2].url.params["rsrcUnqId"] == "EXP_0000000000000050"
    assert requests[2].headers["user-agent"].startswith("UlsanCulture/")
    assert requests[3].url.path.endswith("/expSelectTimeList.do")
    assert parse_qs(requests[3].content.decode()) == {
        "rsrcUnqId": ["EXP_0000000000000050"],
        "rsrcYmd": ["2026-08-11"],
        "mnu_code": ["F401"],
    }
    assert requests[4].url.path.endswith("/dailySelectTimeList.do")
    assert "DateCheck" not in " ".join(request.url.path for request in requests)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_retryable_statuses(status: int):
    assert is_retryable_status(status) is True


@pytest.mark.parametrize("status", [200, 301, 400, 401, 403, 404, 422, 501])
def test_non_retryable_statuses(status: int):
    assert is_retryable_status(status) is False


def test_client_retries_retryable_status_with_exponential_backoff():
    attempts = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, text='<ul class="img-board"><li></li></ul>')

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def scenario() -> None:
        async_client = httpx.AsyncClient(
            base_url="https://ulsan.go.kr", transport=httpx.MockTransport(handler)
        )
        client = UlsanMoaClient(
            http_client=async_client,
            max_retries=2,
            backoff_base_seconds=0.5,
            jitter_seconds=0,
            sleep=fake_sleep,
        )
        await client.fetch_list("F300")
        assert client.request_counts == {"list": 3, "total": 3}
        await async_client.aclose()

    asyncio.run(scenario())

    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_client_detects_waiting_page_even_when_http_status_is_200():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>TRACER waiting page</body></html>")

    async def scenario() -> None:
        async_client = httpx.AsyncClient(
            base_url="https://ulsan.go.kr", transport=httpx.MockTransport(handler)
        )
        client = UlsanMoaClient(http_client=async_client, max_retries=0)
        with pytest.raises(UlsanMoaNetworkError, match="waiting or blocked"):
            await client.fetch_list("F300")
        await async_client.aclose()

    asyncio.run(scenario())


class FakeClient:
    def __init__(self, source_fixture: str, *, detail_error: bool = False) -> None:
        self.source_fixture = source_fixture
        self.detail_error = detail_error
        self.calls: list[tuple[str, object]] = []
        self._counts: Counter[str] = Counter()

    @property
    def request_counts(self) -> dict[str, int]:
        result = dict(self._counts)
        result["total"] = sum(self._counts.values())
        return result

    async def fetch_list(self, source, *, page=1, page_size=12):
        self.calls.append(("list", (source, page, page_size)))
        self._counts["list"] += 1
        return fixture_text(self.source_fixture)

    async def fetch_detail(self, detail_url):
        self.calls.append(("detail", detail_url))
        self._counts["detail"] += 1
        if self.detail_error:
            raise UlsanMoaNetworkError("fixture detail failure", endpoint="detail")
        assert detail_url == EXP_URL
        return fixture_text("exp_detail.html")

    async def fetch_exp_slots(self, *, rsrc_unq_id, rsrc_ymd, mnu_code):
        self.calls.append(("exp_slots", (rsrc_unq_id, rsrc_ymd, mnu_code)))
        self._counts["exp_slots"] += 1
        return fixture_text("exp_time_slots.json")

    async def fetch_day_slots(self, *, rsrc_unq_id, rsrc_ymd, mnu_code="F601"):
        self.calls.append(("day_slots", (rsrc_unq_id, rsrc_ymd, mnu_code)))
        self._counts["day_slots"] += 1
        return fixture_text("day_time_slots.json")


def test_adapter_requests_details_only_for_internal_items():
    client = FakeClient("f300_list.html", detail_error=True)

    result = asyncio.run(UlsanMoaAdapter(client).dry_run("F300"))

    detail_calls = [call for call in client.calls if call[0] == "detail"]
    assert len(detail_calls) == 3
    assert all(str(call[1]).startswith("https://ulsan.go.kr/") for call in detail_calls)
    assert result.summary.internal_count == 3
    assert result.summary.external_count == 9
    assert result.summary.detail_failure_count == 3
    assert all(event.source_event_id is None for event in result.events if event.resource_kind == "external")


def test_adapter_fetches_exp_slots_for_active_dates_only_and_summarizes_dry_run():
    client = FakeClient("f400_list.html")

    result = asyncio.run(UlsanMoaAdapter(client).dry_run("F400"))

    slot_calls = [call for call in client.calls if call[0] == "exp_slots"]
    requested_dates = [call[1][1] for call in slot_calls]
    assert requested_dates == [
        date(2026, 8, 11),
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 17),
        date(2026, 8, 19),
    ]
    assert not [call for call in client.calls if call[0] == "day_slots"]
    assert result.summary.list_count == 12
    assert result.summary.internal_count == 1
    assert result.summary.external_count == 11
    assert result.summary.lec_count == 0
    assert result.summary.exp_count == 1
    assert result.summary.day_count == 0
    assert result.summary.detail_success_count == 1
    assert result.summary.detail_failure_count == 0
    assert result.summary.occurrence_count == 5
    assert result.summary.parser_errors == ()
    assert result.summary.network_errors == ()
    assert result.summary.request_counts == {
        "detail": 1,
        "exp_slots": 5,
        "list": 1,
        "total": 7,
    }
    assert len(result.summary.samples) == 3
    assert "목록 건수: 12" in format_summary(result.summary)
    assert "요청 횟수: detail=1, exp_slots=5, list=1, total=7" in format_summary(
        result.summary
    )


def test_adapter_fetches_day_slots_for_active_dates_only():
    class DayFakeClient(FakeClient):
        async def fetch_list(self, source, *, page=1, page_size=12):
            self.calls.append(("list", (source, page, page_size)))
            self._counts["list"] += 1
            return fixture_text("f400_list.html").replace(
                "EXP_0000000000000050", "DAY_0000000000000000"
            ).replace("mnu_code=F401", "mnu_code=F601")

        async def fetch_detail(self, detail_url):
            self.calls.append(("detail", detail_url))
            self._counts["detail"] += 1
            return fixture_text("day_detail.html")

    client = DayFakeClient("f400_list.html")

    result = asyncio.run(UlsanMoaAdapter(client).dry_run("F400"))

    requested_dates = [
        call[1][1] for call in client.calls if call[0] == "day_slots"
    ]
    assert requested_dates == [
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 15),
        date(2026, 8, 16),
        date(2026, 8, 17),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
        date(2026, 8, 22),
        date(2026, 8, 23),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 29),
        date(2026, 8, 30),
    ]
    assert not [call for call in client.calls if call[0] == "exp_slots"]
    assert result.summary.day_count == 1
    assert result.summary.occurrence_count == 17 * 7


def test_client_rejects_external_detail_before_any_network_request():
    async def scenario() -> None:
        async_client = httpx.AsyncClient(base_url="https://ulsan.go.kr")
        client = UlsanMoaClient(http_client=async_client, max_retries=0)
        with pytest.raises(ValueError, match="internal LEC/EXP/DAY"):
            await client.fetch_detail("https://example.org/events/1")
        assert client.request_counts == {"total": 0}
        await async_client.aclose()

    asyncio.run(scenario())

import asyncio
from collections import Counter
from datetime import UTC, datetime

from app.crawlers.ulsan_moa.adapter import UlsanMoaAdapter
from app.crawlers.ulsan_moa.client import UlsanMoaNetworkError


def list_html(*, page: int, count: int, next_page: int | None, pagination=True) -> str:
    cards = "".join(
        f"""
        <li><a href="https://external.example/{page}/{index}">
          <div class="con-box"><h4 class="tit">행사 {page}-{index}</h4>
          <ul class="info"><li>접수기간: 상시</li><li>모집정원: 가족당 최대 4명</li></ul>
          </div></a></li>
        """
        for index in range(count)
    )
    pagination_html = ""
    if pagination:
        next_link = (
            f'<a class="page-navi next" href="?pageNo={next_page}">다음</a>'
            if next_page is not None
            else ""
        )
        pagination_html = f"""
        <div class="krds-pagination">
          <div class="page-links"><a class="page-link active">{page}</a></div>
          {next_link}
        </div>
        """
    return f'<html><ul class="img-board">{cards}</ul>{pagination_html}</html>'


class PagedClient:
    def __init__(self, pages: dict[int, str | Exception]) -> None:
        self.pages = pages
        self.calls: list[int] = []
        self._counts: Counter[str] = Counter()

    @property
    def request_counts(self):
        counts = dict(self._counts)
        counts["total"] = sum(self._counts.values())
        return counts

    async def fetch_list(self, source, *, page=1, page_size=12):
        self.calls.append(page)
        self._counts["list"] += 1
        value = self.pages[page]
        if isinstance(value, Exception):
            raise value
        return value

    async def fetch_detail(self, detail_url):
        raise AssertionError("external fixture cards must not request details")

    async def fetch_exp_slots(self, **kwargs):
        raise AssertionError("external fixture cards must not request slots")

    async def fetch_day_slots(self, **kwargs):
        raise AssertionError("external fixture cards must not request slots")


def collect(client: PagedClient, *, page_size=2, max_pages=10):
    ticks = iter(
        [
            datetime(2026, 8, 9, 1, tzinfo=UTC),
            datetime(2026, 8, 9, 2, tzinfo=UTC),
        ]
    )

    async def no_sleep(_delay: float) -> None:
        return None

    adapter = UlsanMoaAdapter(client, sleep=no_sleep, now=lambda: next(ticks))
    return asyncio.run(
        adapter.collect_all_pages(
            "F300",
            page_size=page_size,
            max_pages=max_pages,
            page_delay_seconds=0,
            detail_request_delay_seconds=0,
        )
    )


def test_multiple_pages_end_on_short_last_page_as_complete_snapshot():
    client = PagedClient(
        {
            1: list_html(page=1, count=2, next_page=2),
            2: list_html(page=2, count=1, next_page=None, pagination=False),
        }
    )

    result = collect(client)

    assert client.calls == [1, 2]
    assert result.summary.pages_attempted == 2
    assert result.summary.pages_succeeded == 2
    assert result.summary.items_seen == 3
    assert result.summary.status == "success"
    assert result.summary.stop_reason == "short-page"
    assert result.summary.is_complete_snapshot is True


def test_full_last_page_ends_when_pagination_has_no_next_link():
    client = PagedClient(
        {
            1: list_html(page=1, count=2, next_page=2),
            2: list_html(page=2, count=2, next_page=None),
        }
    )

    result = collect(client)

    assert client.calls == [1, 2]
    assert result.summary.stop_reason == "last-page"
    assert result.summary.is_complete_snapshot is True


def test_middle_page_network_failure_is_partial_and_not_complete():
    client = PagedClient(
        {
            1: list_html(page=1, count=2, next_page=2),
            2: UlsanMoaNetworkError("fixture timeout", endpoint="list"),
        }
    )

    result = collect(client)

    assert result.summary.pages_attempted == 2
    assert result.summary.pages_succeeded == 1
    assert result.summary.status == "partial"
    assert result.summary.is_complete_snapshot is False
    assert len(result.summary.network_errors) == 1


def test_middle_page_parser_failure_is_partial_and_not_complete():
    client = PagedClient(
        {
            1: list_html(page=1, count=2, next_page=2),
            2: '<html><ul class="img-board"><li>broken</li></ul></html>',
        }
    )

    result = collect(client)

    assert result.summary.pages_succeeded == 1
    assert result.summary.status == "partial"
    assert result.summary.is_complete_snapshot is False
    assert len(result.summary.parser_errors) == 1


def test_max_page_safety_limit_prevents_false_complete_snapshot():
    client = PagedClient({1: list_html(page=1, count=2, next_page=2)})

    result = collect(client, max_pages=1)

    assert client.calls == [1]
    assert result.summary.status == "partial"
    assert result.summary.stop_reason == "max-pages"
    assert result.summary.is_complete_snapshot is False


def test_short_page_with_next_link_is_pagination_conflict_not_complete():
    client = PagedClient({1: list_html(page=1, count=1, next_page=2)})

    result = collect(client)

    assert result.summary.status == "partial"
    assert result.summary.stop_reason == "pagination-conflict"
    assert result.summary.is_complete_snapshot is False

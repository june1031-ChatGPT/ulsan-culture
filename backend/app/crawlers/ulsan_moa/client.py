from __future__ import annotations

import asyncio
import random
import re
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.crawlers.ulsan_moa.parser import BASE_URL, canonicalize_url


SourceCode = Literal["F300", "F400"]
EndpointName = Literal["list", "detail", "exp_slots", "day_slots"]

DEFAULT_USER_AGENT = (
    "UlsanCulture/0.1 (single-page dry-run crawler; https://ulsan.go.kr source)"
)
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_RESOURCE_ID_PATTERN = re.compile(r"^(LEC|EXP|DAY)_[A-Za-z0-9_]+$")
_BLOCK_PAGE_MARKERS = (
    "tracer waiting",
    "접속 대기 중",
    "접속대기 중",
    "현재 접속자가 많아",
    "요청이 차단되었습니다",
    "서비스 이용이 제한",
    "access denied",
)


class UlsanMoaNetworkError(RuntimeError):
    """Raised when an Ulsan Moa response cannot be fetched safely."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: EndpointName | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code


def is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES


class UlsanMoaClient:
    """Small, rate-limited HTTP client for the public Ulsan Moa pages."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = BASE_URL,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.5,
        jitter_seconds: float = 0.25,
        concurrency: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if base_url.rstrip("/") != BASE_URL:
            raise ValueError(f"base_url must be the non-www host {BASE_URL}")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if concurrency < 1 or concurrency > 2:
            raise ValueError("concurrency must be between 1 and 2")

        self.base_url = BASE_URL
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.jitter_seconds = jitter_seconds
        self._sleep = sleep
        self._random_uniform = random_uniform
        self._semaphore = asyncio.Semaphore(concurrency)
        self._request_counts: Counter[str] = Counter()
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
            },
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            follow_redirects=False,
        )
        self._client.headers["User-Agent"] = DEFAULT_USER_AGENT
        self._client.headers.setdefault(
            "Accept", "text/html,application/json;q=0.9,*/*;q=0.1"
        )

    async def __aenter__(self) -> UlsanMoaClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    @property
    def request_counts(self) -> dict[str, int]:
        counts = dict(self._request_counts)
        counts["total"] = sum(self._request_counts.values())
        return counts

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_list(
        self,
        source: SourceCode,
        *,
        page: int = 1,
        page_size: int = 12,
    ) -> str:
        if source not in {"F300", "F400"}:
            raise ValueError("source must be F300 or F400")
        if page < 1:
            raise ValueError("page must be at least 1")
        if page_size < 1 or page_size > 12:
            raise ValueError("page_size must be between 1 and 12 for a dry-run")
        step = "gallery" if source == "F300" else "list_img"
        response = await self._request(
            "list",
            "GET",
            "/y/yes/page.do",
            params={
                "mnu_code": source,
                "step": step,
                "orderBy": "rcept",
                "pageNo": str(page),
                "pageSize": str(page_size),
            },
        )
        self._validate_html(response.text, selector="ul.img-board", endpoint="list")
        return response.text

    async def fetch_detail(self, detail_url: str) -> str:
        url = self._internal_detail_url(detail_url)
        response = await self._request("detail", "GET", url)
        self._validate_html(
            response.text,
            selector=".reserve-view .view-info",
            endpoint="detail",
        )
        return response.text

    async def fetch_exp_slots(
        self,
        *,
        rsrc_unq_id: str,
        rsrc_ymd: date,
        mnu_code: str,
    ) -> str:
        self._validate_resource(rsrc_unq_id, expected="EXP")
        if not re.fullmatch(r"F4\d{2}", mnu_code):
            raise ValueError("EXP mnu_code must be an F4xx menu code")
        return await self._fetch_slots(
            "exp_slots",
            "/y/common/func/ajax/expSelectTimeList.do",
            rsrc_unq_id=rsrc_unq_id,
            rsrc_ymd=rsrc_ymd,
            mnu_code=mnu_code,
        )

    async def fetch_day_slots(
        self,
        *,
        rsrc_unq_id: str,
        rsrc_ymd: date,
        mnu_code: str = "F601",
    ) -> str:
        self._validate_resource(rsrc_unq_id, expected="DAY")
        if mnu_code != "F601":
            raise ValueError("DAY mnu_code must be F601")
        return await self._fetch_slots(
            "day_slots",
            "/y/common/func/ajax/dailySelectTimeList.do",
            rsrc_unq_id=rsrc_unq_id,
            rsrc_ymd=rsrc_ymd,
            mnu_code=mnu_code,
        )

    async def _fetch_slots(
        self,
        endpoint: Literal["exp_slots", "day_slots"],
        path: str,
        *,
        rsrc_unq_id: str,
        rsrc_ymd: date,
        mnu_code: str,
    ) -> str:
        response = await self._request(
            endpoint,
            "POST",
            path,
            data={
                "rsrcUnqId": rsrc_unq_id,
                "rsrcYmd": rsrc_ymd.isoformat(),
                "mnu_code": mnu_code,
            },
            headers={"Accept": "application/json"},
        )
        self._validate_slot_json(response, endpoint=endpoint)
        return response.text

    async def _request(
        self,
        endpoint: EndpointName,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore:
                    self._request_counts[endpoint] += 1
                    response = await self._client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await self._backoff(attempt)
                    continue
                raise UlsanMoaNetworkError(
                    f"{endpoint} request failed after {attempt + 1} attempt(s): {exc}",
                    endpoint=endpoint,
                ) from exc

            if is_retryable_status(response.status_code) and attempt < self.max_retries:
                await self._backoff(attempt)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise UlsanMoaNetworkError(
                    f"{endpoint} returned HTTP {response.status_code}",
                    endpoint=endpoint,
                    status_code=response.status_code,
                ) from exc
            return response

        raise UlsanMoaNetworkError(
            f"{endpoint} request failed: {last_error}", endpoint=endpoint
        )

    async def _backoff(self, attempt: int) -> None:
        delay = self.backoff_base_seconds * (2**attempt)
        delay += self._random_uniform(0.0, self.jitter_seconds)
        await self._sleep(delay)

    @staticmethod
    def _validate_html(html: str, *, selector: str, endpoint: EndpointName) -> None:
        UlsanMoaClient._reject_block_page(html, endpoint=endpoint)
        if not html.strip():
            raise UlsanMoaNetworkError(f"{endpoint} returned empty HTML", endpoint=endpoint)
        if BeautifulSoup(html, "lxml").select_one(selector) is None:
            raise UlsanMoaNetworkError(
                f"{endpoint} response is missing expected HTML selector {selector}",
                endpoint=endpoint,
            )

    @staticmethod
    def _validate_slot_json(response: httpx.Response, *, endpoint: EndpointName) -> None:
        UlsanMoaClient._reject_block_page(response.text, endpoint=endpoint)
        try:
            payload = response.json()
        except ValueError as exc:
            raise UlsanMoaNetworkError(
                f"{endpoint} response is not valid JSON", endpoint=endpoint
            ) from exc
        if not isinstance(payload, list):
            raise UlsanMoaNetworkError(
                f"{endpoint} response root is not a JSON array", endpoint=endpoint
            )

    @staticmethod
    def _reject_block_page(body: str, *, endpoint: EndpointName) -> None:
        lowered = body.lower()
        marker = next((value for value in _BLOCK_PAGE_MARKERS if value in lowered), None)
        if marker:
            raise UlsanMoaNetworkError(
                f"{endpoint} returned a waiting or blocked page ({marker})",
                endpoint=endpoint,
            )

    @staticmethod
    def _validate_resource(rsrc_unq_id: str, *, expected: str) -> None:
        match = _RESOURCE_ID_PATTERN.fullmatch(rsrc_unq_id)
        if not match or match.group(1) != expected:
            raise ValueError(f"expected {expected} resource ID")

    @staticmethod
    def _internal_detail_url(detail_url: str) -> str:
        canonical = canonicalize_url(detail_url)
        parts = urlsplit(canonical)
        query = parse_qs(parts.query)
        ids = query.get("rsrcUnqId", [])
        if (
            parts.scheme != "https"
            or parts.netloc != "ulsan.go.kr"
            or parts.path != "/y/yes/page.do"
            or len(ids) != 1
            or _RESOURCE_ID_PATTERN.fullmatch(ids[0]) is None
        ):
            raise ValueError("detail_url must identify an internal LEC/EXP/DAY page")
        return canonical

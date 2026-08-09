from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from app.crawlers.ulsan_moa.adapter import UlsanMoaAdapter
from app.crawlers.ulsan_moa.client import UlsanMoaClient
from app.crawlers.ulsan_moa.models import DryRunSummary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="울산모아 안전한 단일 페이지 수집 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    dry_run = subparsers.add_parser("dry-run", help="DB 저장 없이 한 페이지만 수집")
    dry_run.add_argument("--source", type=str.upper, choices=("F300", "F400"), required=True)
    dry_run.add_argument("--page", type=int, default=1)
    dry_run.add_argument("--page-size", type=int, default=12, choices=range(1, 13))
    dry_run.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    ingest = subparsers.add_parser("ingest", help="DB에 한 페이지만 안전하게 저장")
    ingest.add_argument("--source", type=str.upper, choices=("F300", "F400"), required=True)
    ingest.add_argument("--page", type=int, default=1)
    ingest.add_argument("--page-size", type=int, default=12, choices=range(1, 13))
    ingest.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    return parser


async def _run(args: argparse.Namespace) -> DryRunSummary:
    async with UlsanMoaClient() as client:
        result = await UlsanMoaAdapter(client).dry_run(
            args.source, page=args.page, page_size=args.page_size
        )
        return result.summary


async def _run_ingest(args: argparse.Namespace):
    # Keep DB imports out of the dry-run path, including module import side effects.
    from app.crawlers.ulsan_moa.ingest import ingest_collected_page
    from app.database import SessionLocal

    async with UlsanMoaClient() as client:
        result = await UlsanMoaAdapter(client).collect_page(
            args.source, page=args.page, page_size=args.page_size
        )
    return ingest_collected_page(result, session_factory=SessionLocal)


def format_summary(summary: DryRunSummary) -> str:
    lines = [
        f"울산모아 dry-run: {summary.source} page {summary.page}",
        f"목록 건수: {summary.list_count}",
        f"내부/외부: {summary.internal_count}/{summary.external_count}",
        f"LEC/EXP/DAY: {summary.lec_count}/{summary.exp_count}/{summary.day_count}",
        f"상세 성공/실패: {summary.detail_success_count}/{summary.detail_failure_count}",
        f"occurrence 수: {summary.occurrence_count}",
        f"parser 오류: {len(summary.parser_errors)}",
        f"네트워크 오류: {len(summary.network_errors)}",
        "요청 횟수: "
        + ", ".join(f"{key}={value}" for key, value in summary.request_counts.items()),
    ]
    if summary.parser_errors:
        lines.append("parser 오류 상세: " + " | ".join(summary.parser_errors))
    if summary.network_errors:
        lines.append("네트워크 오류 상세: " + " | ".join(summary.network_errors))
    lines.append("대표 정규화 결과:")
    for index, sample in enumerate(summary.samples, start=1):
        lines.append(
            f"[{index}] "
            + json.dumps(sample, ensure_ascii=False, default=_json_default, sort_keys=True)
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest":
        summary = asyncio.run(_run_ingest(args))
        if args.json:
            print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        else:
            print(format_ingest_summary(summary))
        return 0 if summary.fetched_count > 0 and not summary.errors else 1

    summary = asyncio.run(_run(args))
    if args.json:
        print(
            json.dumps(
                asdict(summary), ensure_ascii=False, default=_json_default, indent=2
            )
        )
    else:
        print(format_summary(summary))
    return 0 if summary.list_count > 0 else 1


def format_ingest_summary(summary: Any) -> str:
    lines = [
        f"울산모아 ingest: {summary.source} page {summary.page}",
        f"수집/저장/실패: {summary.fetched_count}/{summary.persisted_count}/{summary.failed_count}",
        f"Event insert/update: {summary.event_inserted_count}/{summary.event_updated_count}",
        "EventOccurrence insert/update: "
        f"{summary.occurrence_inserted_count}/{summary.occurrence_updated_count}",
    ]
    if summary.errors:
        lines.append("오류 상세: " + " | ".join(summary.errors))
    return "\n".join(lines)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())

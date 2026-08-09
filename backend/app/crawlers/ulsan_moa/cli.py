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
    return parser


async def _run(args: argparse.Namespace) -> DryRunSummary:
    async with UlsanMoaClient() as client:
        result = await UlsanMoaAdapter(client).dry_run(
            args.source, page=args.page, page_size=args.page_size
        )
        return result.summary


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


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())

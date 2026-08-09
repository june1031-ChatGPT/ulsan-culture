from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.source import Source


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_crawl_runs_status",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_crawl_runs_time_order",
        ),
        CheckConstraint(
            "pages_attempted >= 0 AND pages_succeeded >= 0 "
            "AND pages_succeeded <= pages_attempted",
            name="ck_crawl_runs_page_counts",
        ),
        CheckConstraint(
            "items_seen >= 0 AND items_persisted >= 0 AND items_failed >= 0",
            name="ck_crawl_runs_item_counts",
        ),
        CheckConstraint(
            "detail_success_count >= 0 AND detail_failure_count >= 0 "
            "AND occurrence_count >= 0",
            name="ck_crawl_runs_detail_counts",
        ),
        CheckConstraint(
            "network_error_count >= 0 AND parser_error_count >= 0",
            name="ck_crawl_runs_error_counts",
        ),
        Index("ix_crawl_runs_source_started", "source_id", "started_at"),
        Index("ix_crawl_runs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)

    pages_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    network_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    is_complete_snapshot: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped["Source"] = relationship(back_populates="crawl_runs")

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event


class EventOccurrence(Base):
    __tablename__ = "event_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "source_occurrence_id",
            name="uq_event_occurrences_event_source_occurrence",
        ),
        CheckConstraint("end_at >= start_at", name="ck_event_occurrences_time_order"),
        CheckConstraint(
            "capacity IS NULL OR capacity >= 0",
            name="ck_event_occurrences_capacity_nonnegative",
        ),
        CheckConstraint(
            "reserved_count IS NULL OR reserved_count >= 0",
            name="ck_event_occurrences_reserved_count_nonnegative",
        ),
        CheckConstraint(
            "available_count IS NULL OR available_count >= 0",
            name="ck_event_occurrences_available_count_nonnegative",
        ),
        CheckConstraint(
            "fee IS NULL OR fee >= 0",
            name="ck_event_occurrences_fee_nonnegative",
        ),
        Index("ix_event_occurrences_event_id", "event_id"),
        Index("ix_event_occurrences_start_at", "start_at"),
        Index("ix_event_occurrences_event_id_start_at", "event_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 단위가 명확하고 동일한 경우에만 정규화한다. 팀/가족/인원 제약은 합산하지 않는다.
    capacity: Mapped[int | None] = mapped_column(Integer)
    reserved_count: Mapped[int | None] = mapped_column(Integer)
    available_count: Mapped[int | None] = mapped_column(Integer)

    fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_free: Mapped[bool | None] = mapped_column(Boolean)
    application_available: Mapped[bool | None] = mapped_column(Boolean)

    source_occurrence_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_raw_data: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    event: Mapped["Event"] = relationship(back_populates="occurrences")

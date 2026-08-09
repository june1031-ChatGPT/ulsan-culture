from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event_occurrence import EventOccurrence
    from app.models.source import Source


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source_id", "source_event_id", name="uq_events_source_event"),
        UniqueConstraint("source_id", "source_item_key", name="uq_events_source_item"),
        CheckConstraint(
            "event_start IS NULL OR event_start_date IS NULL",
            name="ck_events_event_start_precision",
        ),
        CheckConstraint(
            "event_end IS NULL OR event_end_date IS NULL",
            name="ck_events_event_end_precision",
        ),
        CheckConstraint(
            "registration_start IS NULL OR registration_start_date IS NULL",
            name="ck_events_registration_start_precision",
        ),
        CheckConstraint(
            "registration_end IS NULL OR registration_end_date IS NULL",
            name="ck_events_registration_end_precision",
        ),
        CheckConstraint(
            "event_end IS NULL OR event_start IS NULL OR event_end >= event_start",
            name="ck_events_event_datetime_order",
        ),
        CheckConstraint(
            "event_end_date IS NULL OR event_start_date IS NULL "
            "OR event_end_date >= event_start_date",
            name="ck_events_event_date_order",
        ),
        CheckConstraint(
            "registration_end IS NULL OR registration_start IS NULL "
            "OR registration_end >= registration_start",
            name="ck_events_registration_datetime_order",
        ),
        CheckConstraint(
            "registration_end_date IS NULL OR registration_start_date IS NULL "
            "OR registration_end_date >= registration_start_date",
            name="ck_events_registration_date_order",
        ),
        Index("ix_events_event_start", "event_start"),
        Index("ix_events_event_start_date", "event_start_date"),
        Index("ix_events_registration_start", "registration_start"),
        Index("ix_events_registration_start_date", "registration_start_date"),
        Index("ix_events_registration_end", "registration_end"),
        Index("ix_events_registration_end_date", "registration_end_date"),
        Index("ix_events_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organizer: Mapped[str | None] = mapped_column(String(200))
    venue: Mapped[str | None] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(500))
    district: Mapped[str | None] = mapped_column(String(50), index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))

    category: Mapped[str | None] = mapped_column(String(100), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100))
    original_category: Mapped[str | None] = mapped_column(String(200))
    target_text: Mapped[str | None] = mapped_column(Text)
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)

    # 행사 기간과 접수 기간은 제품 원칙에 따라 서로 독립된 필드로 유지한다.
    event_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_start_date: Mapped[date | None] = mapped_column(Date)
    event_end_date: Mapped[date | None] = mapped_column(Date)
    registration_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_start_date: Mapped[date | None] = mapped_column(Date)
    registration_end_date: Mapped[date | None] = mapped_column(Date)
    registration_status: Mapped[str | None] = mapped_column(String(50), index=True)

    application_method: Mapped[str | None] = mapped_column(String(100))
    participation_type: Mapped[str | None] = mapped_column(String(100))
    prerequisite_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prerequisite_text: Mapped[str | None] = mapped_column(Text)
    capacity: Mapped[int | None] = mapped_column(Integer)
    lottery_or_firstcome: Mapped[str | None] = mapped_column(String(50))

    fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_free: Mapped[bool | None] = mapped_column(Boolean)
    reservation_url: Mapped[str | None] = mapped_column(String(2048))
    detail_url: Mapped[str | None] = mapped_column(String(2048))
    image_url: Mapped[str | None] = mapped_column(String(2048))

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_event_id: Mapped[str | None] = mapped_column(String(255))
    source_item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source: Mapped["Source"] = relationship(back_populates="events")
    occurrences: Mapped[list["EventOccurrence"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EventOccurrence.start_at",
    )

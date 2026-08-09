from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    organizer: str | None
    venue: str | None
    address: str | None
    district: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    category: str | None
    subcategory: str | None
    original_category: str | None
    target_text: str | None
    age_min: int | None
    age_max: int | None
    event_start: datetime | None
    event_end: datetime | None
    registration_start: datetime | None
    registration_end: datetime | None
    registration_status: str | None
    application_method: str | None
    participation_type: str | None
    prerequisite_required: bool
    prerequisite_text: str | None
    capacity: int | None
    lottery_or_firstcome: str | None
    fee: Decimal | None
    is_free: bool | None
    reservation_url: str | None
    detail_url: str | None
    image_url: str | None
    source_id: int
    source_event_id: str | None
    source_url: str
    collected_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None
    content_hash: str | None
    is_active: bool


class EventListResponse(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int


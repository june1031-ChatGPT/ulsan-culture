from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.event import Event
from app.schemas.event import EventListResponse, EventRead


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventListResponse)
def list_events(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventListResponse:
    active_filter = Event.is_active.is_(True)
    total = db.scalar(select(func.count(Event.id)).where(active_filter)) or 0
    query = (
        select(Event)
        .where(active_filter)
        .order_by(Event.event_start.asc().nulls_last(), Event.id.asc())
        .offset(offset)
        .limit(limit)
    )
    items = db.scalars(query).all()
    return EventListResponse(
        items=[EventRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )

from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


class EventOccurrenceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_at: AwareDatetime
    end_at: AwareDatetime
    capacity: NonNegativeInt | None = None
    reserved_count: NonNegativeInt | None = None
    available_count: NonNegativeInt | None = None
    fee: NonNegativeDecimal | None = None
    is_free: bool | None = None
    application_available: bool | None = None
    source_occurrence_id: str = Field(min_length=1, max_length=512)
    source_raw_data: dict[str, Any] | list[Any] | None = None

    @model_validator(mode="after")
    def validate_time_order(self) -> Self:
        if self.end_at < self.start_at:
            raise ValueError("end_at must be greater than or equal to start_at")
        return self


class EventOccurrenceCreate(EventOccurrenceBase):
    event_id: int = Field(gt=0)


class EventOccurrenceRead(EventOccurrenceBase):
    id: int
    event_id: int
    collected_at: AwareDatetime
    updated_at: AwareDatetime

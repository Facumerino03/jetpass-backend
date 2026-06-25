from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.flight_plan import FlightPlanPublic


class FplField18Update(BaseModel):
    field: Literal[
        "departure_aerodrome",
        "destination_aerodrome",
        "alternate_aerodrome_1",
        "alternate_aerodrome_2",
    ]
    from_value: str | None = None
    to_value: str
    reason: str | None = None


class FplField18Result(BaseModel):
    computed_field18: str = ""
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    fpl_updates: list[FplField18Update] = Field(default_factory=list)
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class FlightPlanField18PreviewResponse(BaseModel):
    intent: str
    field18: FplField18Result


class FlightPlanField18ApplyResponse(BaseModel):
    plan: FlightPlanPublic
    field18: FplField18Result

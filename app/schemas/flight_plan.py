from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlanStatus, FlightRules, FlightType
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.services.flight_plan_validations import ensure_valid_icao_code


class PilotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str


class FlightPlanCreate(BaseModel):
    departure_aerodrome_icao: str = Field(min_length=4, max_length=4)
    departure_eobt_utc: datetime
    destination_aerodrome_icao: str = Field(min_length=4, max_length=4)
    alternate1_aerodrome_icao: str = Field(min_length=4, max_length=4)
    alternate2_aerodrome_icao: str = Field(min_length=4, max_length=4)

    @field_validator("departure_aerodrome_icao", "destination_aerodrome_icao", "alternate1_aerodrome_icao", "alternate2_aerodrome_icao")
    @classmethod
    def normalize_icao(cls, value: str) -> str:
        return ensure_valid_icao_code(value)


class FlightPlanUpdate(BaseModel):
    flight_rules: FlightRules | None = None
    flight_type: FlightType | None = None
    aircraft_id: UUID | None = None
    aircraft_identification_snapshot: str | None = Field(default=None, min_length=1, max_length=20)
    aircraft_type_designator_snapshot: str | None = Field(default=None, min_length=1, max_length=10)
    wake_turbulence_category_snapshot: WakeTurbulenceCat | None = None
    equipment_com_nav_snapshot: str | None = Field(default=None, min_length=1, max_length=80)
    equipment_surveillance_snapshot: str | None = Field(default=None, min_length=1, max_length=80)
    emergency_radio_snapshot: str | None = Field(default=None, max_length=20)
    survival_equipment_snapshot: str | None = Field(default=None, max_length=20)
    life_jackets_snapshot: str | None = Field(default=None, max_length=20)
    dinghies_number_snapshot: int | None = Field(default=None, ge=0)
    dinghies_capacity_snapshot: int | None = Field(default=None, ge=0)
    dinghies_cover_snapshot: bool | None = None
    dinghies_color_snapshot: str | None = Field(default=None, max_length=40)
    color_and_markings_snapshot: str | None = Field(default=None, min_length=1, max_length=255)
    cruising_speed: str | None = Field(default=None, min_length=1, max_length=5)
    cruising_level: str | None = Field(default=None, min_length=1, max_length=5)
    route: str | None = Field(default=None, min_length=1)
    rule_change_point: str | None = Field(default=None, max_length=40)
    total_eet: str | None = Field(default=None, min_length=4, max_length=4)
    other_information: str | None = None
    endurance: str | None = Field(default=None, min_length=4, max_length=4)
    persons_on_board: int | None = Field(default=None, ge=1)


class FlightPlanSubmitResponse(BaseModel):
    id: UUID
    status: FlightPlanStatus


class FlightPlanDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class FlightPlanApprovalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor: FlightPlanApprovalActor
    criterion: str
    status: FlightPlanApprovalStatus
    approved_by_user_id: UUID | None
    rejected_by_user_id: UUID | None
    reason: str | None
    decided_at: datetime | None


class FlightPlanStatusHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_status: FlightPlanStatus | None
    to_status: FlightPlanStatus
    updated_by_user_id: UUID | None
    reason: str | None
    created_at: datetime


class FlightPlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pilot: PilotSummary
    pilot_user_id: UUID
    aircraft_id: UUID | None
    status: FlightPlanStatus
    flight_rules: FlightRules | None
    flight_type: FlightType | None
    departure_aerodrome_icao: str
    departure_eobt_utc: datetime
    destination_aerodrome_icao: str
    alternate1_aerodrome_icao: str
    alternate2_aerodrome_icao: str
    cruising_speed: str | None
    cruising_level: str | None
    route: str | None
    rule_change_point: str | None
    total_eet: str | None
    other_information: str | None
    endurance: str | None
    persons_on_board: int | None
    aircraft_identification_snapshot: str | None
    aircraft_type_designator_snapshot: str | None
    wake_turbulence_category_snapshot: WakeTurbulenceCat | None
    equipment_com_nav_snapshot: str | None
    equipment_surveillance_snapshot: str | None
    emergency_radio_snapshot: str | None
    survival_equipment_snapshot: str | None
    life_jackets_snapshot: str | None
    dinghies_number_snapshot: int | None
    dinghies_capacity_snapshot: int | None
    dinghies_cover_snapshot: bool | None
    dinghies_color_snapshot: str | None
    color_and_markings_snapshot: str | None
    aircraft_snapshot_confirmed_at: datetime | None
    approvals: list[FlightPlanApprovalPublic] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FlightPlanDetailPublic(FlightPlanPublic):
    approvals: list[FlightPlanApprovalPublic] = Field(default_factory=list)
    status_history: list[FlightPlanStatusHistoryPublic] = Field(default_factory=list)

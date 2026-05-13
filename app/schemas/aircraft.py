from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.aircraft import WakeTurbulenceCat


class AircraftCreate(BaseModel):
    identification: str = Field(min_length=1, max_length=20)
    icao_type_designator: str = Field(min_length=1, max_length=10)
    wake_turbulence_category: WakeTurbulenceCat
    equipment_com_nav: str = Field(min_length=1, max_length=80)
    equipment_surveillance: str = Field(min_length=1, max_length=80)
    color_and_markings: str = Field(min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=120)
    pbn_capabilities: str | None = Field(default=None, max_length=80)
    emergency_radio: str | None = Field(default=None, max_length=20)
    survival_equipment: str | None = Field(default=None, max_length=20)
    life_jackets: str | None = Field(default=None, max_length=20)
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover: bool | None = None
    dinghies_color: str | None = Field(default=None, max_length=40)


class AircraftUpdate(BaseModel):
    identification: str = Field(default=None, min_length=1, max_length=20)
    icao_type_designator: str = Field(default=None, min_length=1, max_length=10)
    wake_turbulence_category: WakeTurbulenceCat = None
    equipment_com_nav: str = Field(default=None, min_length=1, max_length=80)
    equipment_surveillance: str = Field(default=None, min_length=1, max_length=80)
    color_and_markings: str = Field(default=None, min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=120)
    pbn_capabilities: str | None = Field(default=None, max_length=80)
    emergency_radio: str | None = Field(default=None, max_length=20)
    survival_equipment: str | None = Field(default=None, max_length=20)
    life_jackets: str | None = Field(default=None, max_length=20)
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover: bool | None = None
    dinghies_color: str | None = Field(default=None, max_length=40)


class AircraftPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    alias: str | None
    is_active: bool
    identification: str
    icao_type_designator: str
    wake_turbulence_category: str
    equipment_com_nav: str
    equipment_surveillance: str
    pbn_capabilities: str | None
    emergency_radio: str | None
    survival_equipment: str | None
    life_jackets: str | None
    dinghies_number: int | None
    dinghies_capacity: int | None
    dinghies_cover: bool | None
    dinghies_color: str | None
    color_and_markings: str
    created_at: datetime
    updated_at: datetime


class AircraftDeleteResponse(BaseModel):
    deleted: bool

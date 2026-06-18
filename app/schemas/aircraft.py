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
    emergency_radio_uhf: bool = False
    emergency_radio_vhf: bool = False
    emergency_radio_elt: bool = False
    survival_equipment_present: bool = False
    survival_polar: bool = False
    survival_desert: bool = False
    survival_maritime: bool = False
    survival_jungle: bool = False
    life_jackets_present: bool = False
    life_jackets_lights: bool = False
    life_jackets_fluorescein: bool = False
    life_jackets_uhf: bool = False
    life_jackets_vhf: bool = False
    dinghies_present: bool = False
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover_present: bool = False
    dinghies_color: str | None = Field(default=None, max_length=40)
    image_url: str | None = Field(default=None, max_length=512)


class AircraftUpdate(BaseModel):
    identification: str | None = Field(default=None, min_length=1, max_length=20)
    icao_type_designator: str | None = Field(default=None, min_length=1, max_length=10)
    wake_turbulence_category: WakeTurbulenceCat | None = None
    equipment_com_nav: str | None = Field(default=None, min_length=1, max_length=80)
    equipment_surveillance: str | None = Field(default=None, min_length=1, max_length=80)
    color_and_markings: str | None = Field(default=None, min_length=1, max_length=255)
    alias: str | None = Field(default=None, max_length=120)
    pbn_capabilities: str | None = Field(default=None, max_length=80)
    emergency_radio_uhf: bool | None = None
    emergency_radio_vhf: bool | None = None
    emergency_radio_elt: bool | None = None
    survival_equipment_present: bool | None = None
    survival_polar: bool | None = None
    survival_desert: bool | None = None
    survival_maritime: bool | None = None
    survival_jungle: bool | None = None
    life_jackets_present: bool | None = None
    life_jackets_lights: bool | None = None
    life_jackets_fluorescein: bool | None = None
    life_jackets_uhf: bool | None = None
    life_jackets_vhf: bool | None = None
    dinghies_present: bool | None = None
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover_present: bool | None = None
    dinghies_color: str | None = Field(default=None, max_length=40)
    image_url: str | None = Field(default=None, max_length=512)


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
    emergency_radio_uhf: bool
    emergency_radio_vhf: bool
    emergency_radio_elt: bool
    survival_equipment_present: bool
    survival_polar: bool
    survival_desert: bool
    survival_maritime: bool
    survival_jungle: bool
    life_jackets_present: bool
    life_jackets_lights: bool
    life_jackets_fluorescein: bool
    life_jackets_uhf: bool
    life_jackets_vhf: bool
    dinghies_present: bool
    dinghies_number: int | None
    dinghies_capacity: int | None
    dinghies_cover_present: bool
    dinghies_color: str | None
    color_and_markings: str
    image_url: str | None
    created_at: datetime
    updated_at: datetime


class AircraftDeleteResponse(BaseModel):
    deleted: bool

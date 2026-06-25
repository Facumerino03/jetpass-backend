from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.services.flight_plan_validations import ensure_valid_icao_code


class AerodromeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


class AerodromePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    local_identifier: str
    icao_code: str | None
    name: str
    latitude: float
    longitude: float
    is_controlled: bool
    is_active: bool

    @computed_field
    @property
    def location_code(self) -> str:
        return self.icao_code or self.local_identifier


class AerodromeCatalogSyncRequest(BaseModel):
    force_refresh: bool = False


class AerodromeCatalogSyncResult(BaseModel):
    upserted: int
    deleted: int
    source: str | None = None
    synced_at: str | None = None
    total_listed: int | None = None
    total_aerodromes: int | None = None
    total_helipuertos_skipped: int | None = None
    total_without_icao: int | None = None
    alerts: list[dict] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class AerodromeCatalogItem(BaseModel):
    local_identifier: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=160)
    latitude: float
    longitude: float
    is_controlled: bool
    icao_code: str | None = Field(default=None, min_length=4, max_length=4)

    @field_validator("icao_code")
    @classmethod
    def normalize_icao(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_valid_icao_code(value)

    @field_validator("local_identifier")
    @classmethod
    def normalize_local_identifier(cls, value: str) -> str:
        return value.strip().upper()

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.flight_plan_validations import ensure_valid_icao_code


class ControlledAerodromeCreate(BaseModel):
    icao_code: str = Field(min_length=4, max_length=4)
    name: str = Field(min_length=1, max_length=160)
    is_active: bool = True
    traffic_type: str | None = Field(default=None, max_length=20)
    flight_rules: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=20)

    @field_validator("icao_code")
    @classmethod
    def normalize_icao(cls, value: str) -> str:
        return ensure_valid_icao_code(value)


class ControlledAerodromeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None
    traffic_type: str | None = Field(default=None, max_length=20)
    flight_rules: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=20)


class ControlledAerodromePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    icao_code: str
    name: str
    is_active: bool
    traffic_type: str | None = None
    flight_rules: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class ControlledAerodromeJSONImport(BaseModel):
    items: list[ControlledAerodromeCreate] = Field(min_length=1)


class ControlledAerodromeCSVImport(BaseModel):
    content: str = Field(min_length=1)


class ControlledAerodromeImportResult(BaseModel):
    upserted: int

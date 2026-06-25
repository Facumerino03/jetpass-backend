from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.services.flight_plan_validations import ensure_valid_icao_code


class IntelligenceAerodromeRequest(BaseModel):
    icao: str | None = Field(default=None, min_length=4, max_length=4)
    icaos: list[str] | None = None
    force_refresh: bool = False

    @field_validator("icao")
    @classmethod
    def normalize_icao(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ensure_valid_icao_code(value)

    @field_validator("icaos")
    @classmethod
    def normalize_icaos(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [ensure_valid_icao_code(v) for v in value]


class IntelligenceCatalogSyncRequest(BaseModel):
    force_refresh: bool = False


class IntelligenceRunRequest(BaseModel):
    aerodrome: IntelligenceAerodromeRequest | None = None
    notam: IntelligenceAerodromeRequest | None = None
    weather: IntelligenceAerodromeRequest | None = None
    aerodrome_geo: IntelligenceAerodromeRequest | None = None
    aerodrome_catalog_sync: IntelligenceCatalogSyncRequest | None = None


class IntelligenceRunResponse(BaseModel):
    intent: str
    aerodrome: dict[str, Any] | None = None
    notam: dict[str, Any] | None = None
    weather: dict[str, Any] | None = None
    aerodrome_geo: dict[str, Any] | None = None
    aerodrome_catalog_sync: dict[str, Any] | None = None
    fpl_field18: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}

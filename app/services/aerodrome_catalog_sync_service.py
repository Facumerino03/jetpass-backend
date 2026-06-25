from __future__ import annotations

from fastapi import HTTPException, status

from app.repositories.aerodrome_repository import AerodromeRepository
from app.schemas.aerodrome import (
    AerodromeCatalogItem,
    AerodromeCatalogSyncResult,
)
from app.services.intelligence_client import IntelligenceClient
from sqlalchemy.ext.asyncio import AsyncSession


class AerodromeCatalogSyncService:
    def __init__(self, *, intelligence_client: IntelligenceClient | None = None) -> None:
        self._intelligence_client = intelligence_client

    def _client(self) -> IntelligenceClient:
        if self._intelligence_client is None:
            from app.core.config import settings

            return IntelligenceClient(
                base_url=settings.INTELLIGENCE_BASE_URL,
                timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS,
            )
        return self._intelligence_client

    async def sync_catalog(
        self,
        db: AsyncSession,
        *,
        force_refresh: bool,
    ) -> AerodromeCatalogSyncResult:
        response = await self._client().run(
            {"aerodrome_catalog_sync": {"force_refresh": force_refresh}}
        )
        if response.get("intent") == "unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Aerodrome catalog sync is unavailable",
            )

        payload = response.get("aerodrome_catalog_sync")
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid aerodrome catalog sync response from intelligence",
            )

        raw_aerodromes = payload.get("aerodromes") or []
        items = [AerodromeCatalogItem.model_validate(item).model_dump() for item in raw_aerodromes]
        upserted, deleted = await AerodromeRepository.replace_from_sync(db, items=items)
        await db.commit()

        return AerodromeCatalogSyncResult(
            upserted=upserted,
            deleted=deleted,
            source=payload.get("source"),
            synced_at=payload.get("synced_at"),
            total_listed=payload.get("total_listed"),
            total_aerodromes=payload.get("total_aerodromes"),
            total_helipuertos_skipped=payload.get("total_helipuertos_skipped"),
            total_without_icao=payload.get("total_without_icao"),
            alerts=payload.get("alerts") or [],
            messages=payload.get("messages") or [],
        )

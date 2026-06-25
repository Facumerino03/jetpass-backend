import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.repositories.aerodrome_repository import AerodromeRepository
from app.services.aerodrome_catalog_sync_service import AerodromeCatalogSyncService
from app.services.intelligence_client import IntelligenceClient


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_catalog_persists_aerodromes_and_deletes_stale(db_session):
    await AerodromeRepository.create(
        db_session,
        local_identifier="OLD",
        icao_code="OLDX",
        name="Old",
        latitude=0.0,
        longitude=0.0,
        is_controlled=True,
    )
    await db_session.commit()

    class FakeIntelligenceClient:
        async def run(self, payload):
            return {
                "intent": "aerodrome_catalog_sync",
                "aerodrome_catalog_sync": {
                    "source": "fresh_fetch",
                    "synced_at": "2026-06-24T12:00:00Z",
                    "aerodromes": [
                        {
                            "local_identifier": "SVO",
                            "icao_code": "SAAV",
                            "name": "Santa Fe / Sauce Viejo",
                            "latitude": -31.7108,
                            "longitude": -60.8114,
                            "is_controlled": True,
                        }
                    ],
                    "alerts": [],
                    "messages": [],
                },
            }

    service = AerodromeCatalogSyncService(intelligence_client=FakeIntelligenceClient())
    result = await service.sync_catalog(db_session, force_refresh=True)

    assert result.upserted == 1
    assert result.deleted == 1
    assert result.source == "fresh_fetch"

    synced = await AerodromeRepository.get_by_local_identifier(db_session, local_identifier="SVO")
    assert synced is not None
    assert synced.icao_code == "SAAV"


@pytest.mark.asyncio
async def test_sync_catalog_raises_when_intelligence_unavailable(db_session):
    class UnavailableClient(IntelligenceClient):
        async def run(self, payload):
            return self.unavailable_response()

    service = AerodromeCatalogSyncService(intelligence_client=UnavailableClient(base_url=None, timeout_seconds=1.0))

    with pytest.raises(HTTPException) as exc:
        await service.sync_catalog(db_session, force_refresh=False)

    assert exc.value.status_code == 503

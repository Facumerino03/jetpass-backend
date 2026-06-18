import csv
from io import StringIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.models.user import Role
from app.repositories.controlled_aerodrome_repository import ControlledAerodromeRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.schemas.controlled_aerodrome import (
    ControlledAerodromeCSVImport,
    ControlledAerodromeCreate,
    ControlledAerodromeImportResult,
    ControlledAerodromeJSONImport,
    ControlledAerodromePublic,
    ControlledAerodromeUpdate,
)
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanDecisionRequest, FlightPlanDetailPublic, FlightPlanPublic, FlightPlanSubmitResponse, FlightPlanUpdate
from app.schemas.intelligence import IntelligenceAerodromeRequest, IntelligenceRunRequest, IntelligenceRunResponse
from app.services.flight_plan_service import FlightPlanService
from app.services.intelligence_client import IntelligenceClient
from app.core.config import settings

router = APIRouter(prefix="/flight-plans", tags=["flight-plans"])


async def _enrich_coordinates(db: AsyncSession, icao_codes: list[str]) -> None:
    missing = []
    for icao_code in icao_codes:
        aerodrome = await ControlledAerodromeRepository.get_by_icao(db, icao_code=icao_code)
        if aerodrome is not None and aerodrome.latitude is None:
            missing.append(aerodrome)
    if not missing:
        return
    client = IntelligenceClient(
        base_url=settings.INTELLIGENCE_BASE_URL,
        timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS,
    )
    response = await client.run({"aerodrome_geo": {"icaos": [a.icao_code for a in missing], "force_refresh": False}})
    geo_data = response.get("aerodrome_geo") or {}
    for aerodrome in missing:
        coord = geo_data.get(aerodrome.icao_code, {})
        lat = coord.get("lat")
        lon = coord.get("lon")
        if lat is not None and lon is not None:
            await ControlledAerodromeRepository.update(aerodrome, latitude=lat, longitude=lon)


def _ensure_catalog_manager(current_user) -> None:
    if current_user.role not in {Role.ADMIN, Role.ATC_AUTHORITY}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and authorities can manage controlled aerodromes",
        )


@router.post("/intelligence/aerodrome")
async def flight_plan_aerodrome_intelligence(payload: IntelligenceAerodromeRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    response = await client.run({"aerodrome": payload.model_dump()})
    return IntelligenceRunResponse.model_validate(response)


@router.post("/intelligence/notam")
async def flight_plan_notam_intelligence(payload: IntelligenceAerodromeRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    response = await client.run({"notam": payload.model_dump()})
    return IntelligenceRunResponse.model_validate(response)


@router.post("/intelligence/weather")
async def flight_plan_weather_intelligence(payload: IntelligenceAerodromeRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    response = await client.run({"weather": payload.model_dump()})
    return IntelligenceRunResponse.model_validate(response)


@router.post("/intelligence/aerodrome-geo")
async def flight_plan_aerodrome_geo_intelligence(payload: IntelligenceAerodromeRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    body = payload.model_dump(exclude_none=True)
    response = await client.run({"aerodrome_geo": body})
    return IntelligenceRunResponse.model_validate(response)


@router.post("/intelligence/run")
async def flight_plan_run_intelligence(payload: IntelligenceRunRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    response = await client.run(payload.model_dump(exclude_none=True))
    return IntelligenceRunResponse.model_validate(response)


@router.get("/aerodromes")
async def list_controlled_aerodromes_for_flight_plan(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    query: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> list[ControlledAerodromePublic]:
    aerodromes = await ControlledAerodromeRepository.list_active(db, query=query, limit=limit)
    return [ControlledAerodromePublic.model_validate(item) for item in aerodromes]


@router.get("/admin/aerodromes")
async def list_controlled_aerodromes_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[ControlledAerodromePublic]:
    _ensure_catalog_manager(current_user)
    aerodromes = await ControlledAerodromeRepository.list_all(db)
    return [ControlledAerodromePublic.model_validate(item) for item in aerodromes]


@router.post("/admin/aerodromes", status_code=status.HTTP_201_CREATED)
async def create_controlled_aerodrome(
    payload: ControlledAerodromeCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ControlledAerodromePublic:
    _ensure_catalog_manager(current_user)
    existing = await ControlledAerodromeRepository.get_by_icao(db, icao_code=payload.icao_code)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Controlled aerodrome already exists")
    aerodrome = await ControlledAerodromeRepository.create(db, **payload.model_dump())
    await db.commit()
    await db.refresh(aerodrome)
    await _enrich_coordinates(db, [aerodrome.icao_code])
    await db.commit()
    await db.refresh(aerodrome)
    return ControlledAerodromePublic.model_validate(aerodrome)


@router.patch("/admin/aerodromes/{icao_code}")
async def update_controlled_aerodrome(
    icao_code: str,
    payload: ControlledAerodromeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ControlledAerodromePublic:
    _ensure_catalog_manager(current_user)
    aerodrome = await ControlledAerodromeRepository.get_by_icao(db, icao_code=icao_code)
    if aerodrome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Controlled aerodrome not found")
    await ControlledAerodromeRepository.update(aerodrome, **payload.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(aerodrome)
    return ControlledAerodromePublic.model_validate(aerodrome)


@router.delete("/admin/aerodromes/{icao_code}")
async def deactivate_controlled_aerodrome(
    icao_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ControlledAerodromePublic:
    _ensure_catalog_manager(current_user)
    aerodrome = await ControlledAerodromeRepository.get_by_icao(db, icao_code=icao_code)
    if aerodrome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Controlled aerodrome not found")
    await ControlledAerodromeRepository.update(aerodrome, is_active=False)
    await db.commit()
    await db.refresh(aerodrome)
    return ControlledAerodromePublic.model_validate(aerodrome)


@router.post("/admin/aerodromes/import/json")
async def import_controlled_aerodromes_json(
    payload: ControlledAerodromeJSONImport,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ControlledAerodromeImportResult:
    _ensure_catalog_manager(current_user)
    upserted = await ControlledAerodromeRepository.upsert_many(
        db,
        items=[item.model_dump() for item in payload.items],
    )
    await db.commit()
    icao_codes = [item.icao_code.upper() for item in payload.items]
    await _enrich_coordinates(db, icao_codes)
    await db.commit()
    return ControlledAerodromeImportResult(upserted=upserted)


@router.post("/admin/aerodromes/import/csv")
async def import_controlled_aerodromes_csv(
    payload: ControlledAerodromeCSVImport,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ControlledAerodromeImportResult:
    _ensure_catalog_manager(current_user)
    reader = csv.DictReader(StringIO(payload.content))
    items = []
    for row in reader:
        is_active_value = (row.get("is_active") or "true").strip().lower()
        items.append(
            {
                "icao_code": row["icao_code"],
                "name": row["name"],
                "is_active": is_active_value in {"true", "1", "yes", "si", "sí"},
            }
        )
    upserted = await ControlledAerodromeRepository.upsert_many(db, items=items)
    await db.commit()
    icao_codes = [row["icao_code"].upper() for row in items]
    await _enrich_coordinates(db, icao_codes)
    await db.commit()
    return ControlledAerodromeImportResult(upserted=upserted)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flight_plan(
    payload: FlightPlanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.create_draft(db, current_user, payload)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=plan.id)
    return FlightPlanPublic.model_validate(plan)


@router.get("")
async def list_flight_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[FlightPlanPublic]:
    plans = await FlightPlanService.list_visible(db, current_user)
    return [FlightPlanPublic.model_validate(plan) for plan in plans]


@router.get("/{flight_plan_id}")
async def get_flight_plan(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanDetailPublic:
    plan = await FlightPlanService.get_visible(db, current_user, flight_plan_id)
    return FlightPlanDetailPublic.model_validate(plan)


@router.patch("/{flight_plan_id}")
async def update_flight_plan(
    flight_plan_id: UUID,
    payload: FlightPlanUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.update_draft(db, current_user, flight_plan_id, payload)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=plan.id)
    return FlightPlanPublic.model_validate(plan)


@router.post("/{flight_plan_id}/submit")
async def submit_flight_plan(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanSubmitResponse:
    plan = await FlightPlanService.submit(db, current_user, flight_plan_id)
    return FlightPlanSubmitResponse(id=plan.id, status=plan.status)


@router.post("/{flight_plan_id}/approve")
async def approve_flight_plan(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanSubmitResponse:
    plan = await FlightPlanService.approve(db, current_user, flight_plan_id)
    return FlightPlanSubmitResponse(id=plan.id, status=plan.status)


@router.post("/{flight_plan_id}/reject")
async def reject_flight_plan(
    flight_plan_id: UUID,
    payload: FlightPlanDecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanSubmitResponse:
    plan = await FlightPlanService.reject(db, current_user, flight_plan_id, reason=payload.reason or "")
    return FlightPlanSubmitResponse(id=plan.id, status=plan.status)

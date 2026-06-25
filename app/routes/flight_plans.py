from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.models.user import Role
from app.repositories.aerodrome_repository import AerodromeRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.schemas.aerodrome import (
    AerodromeCatalogSyncRequest,
    AerodromeCatalogSyncResult,
    AerodromePublic,
    AerodromeUpdate,
)
from app.schemas.flight_plan import (
    FlightPlanCreate,
    FlightPlanDecisionRequest,
    FlightPlanDetailPublic,
    FlightPlanOfficialPdfUrlResponse,
    FlightPlanPublic,
    FlightPlanSignaturePresignRequest,
    FlightPlanSignaturePresignResponse,
    FlightPlanSubmitResponse,
    FlightPlanUpdate,
)
from app.schemas.fpl_field18 import FlightPlanField18ApplyResponse, FlightPlanField18PreviewResponse
from app.schemas.intelligence import IntelligenceAerodromeRequest, IntelligenceRunRequest, IntelligenceRunResponse
from app.services.aerodrome_catalog_sync_service import AerodromeCatalogSyncService
from app.services.flight_plan_field18_service import FlightPlanField18Service
from app.services.flight_plan_official_pdf_service import FlightPlanOfficialPdfService
from app.services.flight_plan_service import FlightPlanService
from app.services.flight_plan_signature_service import FlightPlanSignatureService
from app.services.intelligence_client import IntelligenceClient
from app.core.config import settings

router = APIRouter(prefix="/flight-plans", tags=["flight-plans"])


def get_flight_plan_signature_service() -> FlightPlanSignatureService:
    return FlightPlanService._get_signature_service()


FlightPlanSignatureServiceDep = Annotated[FlightPlanSignatureService, Depends(get_flight_plan_signature_service)]


def get_flight_plan_official_pdf_service() -> FlightPlanOfficialPdfService:
    return FlightPlanService._get_official_pdf_service()


FlightPlanOfficialPdfServiceDep = Annotated[
    FlightPlanOfficialPdfService,
    Depends(get_flight_plan_official_pdf_service),
]


def get_aerodrome_catalog_sync_service() -> AerodromeCatalogSyncService:
    return AerodromeCatalogSyncService()


AerodromeCatalogSyncServiceDep = Annotated[
    AerodromeCatalogSyncService,
    Depends(get_aerodrome_catalog_sync_service),
]


def get_flight_plan_field18_service() -> FlightPlanField18Service:
    return FlightPlanField18Service()


FlightPlanField18ServiceDep = Annotated[
    FlightPlanField18Service,
    Depends(get_flight_plan_field18_service),
]


def _ensure_catalog_manager(current_user) -> None:
    if current_user.role not in {Role.ADMIN, Role.ATC_AUTHORITY}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and authorities can manage aerodromes",
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
async def list_aerodromes_for_flight_plan(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    query: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> list[AerodromePublic]:
    aerodromes = await AerodromeRepository.list_active_for_flight_plan(db, query=query, limit=limit)
    return [AerodromePublic.model_validate(item) for item in aerodromes]


@router.get("/admin/aerodromes")
async def list_aerodromes_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    is_controlled: Annotated[bool | None, Query()] = None,
) -> list[AerodromePublic]:
    _ensure_catalog_manager(current_user)
    aerodromes = await AerodromeRepository.list_all(db, is_controlled=is_controlled)
    return [AerodromePublic.model_validate(item) for item in aerodromes]


@router.post("/admin/aerodromes/sync")
async def sync_aerodromes_catalog(
    payload: AerodromeCatalogSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    sync_service: AerodromeCatalogSyncServiceDep,
) -> AerodromeCatalogSyncResult:
    _ensure_catalog_manager(current_user)
    return await sync_service.sync_catalog(db, force_refresh=payload.force_refresh)


@router.patch("/admin/aerodromes/{local_identifier}")
async def update_aerodrome(
    local_identifier: str,
    payload: AerodromeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AerodromePublic:
    _ensure_catalog_manager(current_user)
    aerodrome = await AerodromeRepository.get_by_local_identifier(
        db,
        local_identifier=local_identifier,
    )
    if aerodrome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aerodrome not found")
    await AerodromeRepository.update(aerodrome, **payload.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(aerodrome)
    return AerodromePublic.model_validate(aerodrome)


@router.delete("/admin/aerodromes/{local_identifier}")
async def deactivate_aerodrome(
    local_identifier: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AerodromePublic:
    _ensure_catalog_manager(current_user)
    aerodrome = await AerodromeRepository.get_by_local_identifier(
        db,
        local_identifier=local_identifier,
    )
    if aerodrome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aerodrome not found")
    await AerodromeRepository.update(aerodrome, is_active=False)
    await db.commit()
    await db.refresh(aerodrome)
    return AerodromePublic.model_validate(aerodrome)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flight_plan(
    payload: FlightPlanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    signature_service: FlightPlanSignatureServiceDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.create_draft(db, current_user, payload)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=plan.id)
    return FlightPlanPublic.from_model(
        plan,
        signature_service=signature_service,
        official_pdf_service=official_pdf_service,
    )


@router.get("")
async def list_flight_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    signature_service: FlightPlanSignatureServiceDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> list[FlightPlanPublic]:
    plans = await FlightPlanService.list_visible(db, current_user)
    return [
        FlightPlanPublic.from_model(
            plan,
            signature_service=signature_service,
            official_pdf_service=official_pdf_service,
        )
        for plan in plans
    ]


@router.get("/{flight_plan_id}")
async def get_flight_plan(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    signature_service: FlightPlanSignatureServiceDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> FlightPlanDetailPublic:
    plan = await FlightPlanService.get_visible(db, current_user, flight_plan_id)
    return FlightPlanDetailPublic.from_model(
        plan,
        signature_service=signature_service,
        official_pdf_service=official_pdf_service,
    )


@router.post("/{flight_plan_id}/signature/presign")
async def presign_flight_plan_signature(
    flight_plan_id: UUID,
    payload: FlightPlanSignaturePresignRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanSignaturePresignResponse:
    result = await FlightPlanService.presign_signature(
        db,
        current_user,
        flight_plan_id,
        payload.content_type,
    )
    return FlightPlanSignaturePresignResponse.model_validate(result)


@router.patch("/{flight_plan_id}")
async def update_flight_plan(
    flight_plan_id: UUID,
    payload: FlightPlanUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    signature_service: FlightPlanSignatureServiceDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.update_draft(db, current_user, flight_plan_id, payload)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=plan.id)
    return FlightPlanPublic.from_model(
        plan,
        signature_service=signature_service,
        official_pdf_service=official_pdf_service,
    )


@router.post("/{flight_plan_id}/field18/preview")
async def preview_flight_plan_field18(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    field18_service: FlightPlanField18ServiceDep,
) -> FlightPlanField18PreviewResponse:
    intent, field18 = await field18_service.preview(db, current_user, flight_plan_id)
    return FlightPlanField18PreviewResponse(intent=intent, field18=field18)


@router.post("/{flight_plan_id}/field18/apply")
async def apply_flight_plan_field18(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    field18_service: FlightPlanField18ServiceDep,
    signature_service: FlightPlanSignatureServiceDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> FlightPlanField18ApplyResponse:
    plan, field18 = await field18_service.apply(db, current_user, flight_plan_id)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=plan.id)
    return FlightPlanField18ApplyResponse(
        plan=FlightPlanPublic.from_model(
            plan,
            signature_service=signature_service,
            official_pdf_service=official_pdf_service,
        ),
        field18=field18,
    )


@router.get("/{flight_plan_id}/official-pdf")
async def get_flight_plan_official_pdf(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    official_pdf_service: FlightPlanOfficialPdfServiceDep,
) -> FlightPlanOfficialPdfUrlResponse:
    plan = await FlightPlanService.get_visible(db, current_user, flight_plan_id)
    if plan.official_pdf_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Official PDF not found")
    official_pdf_url = official_pdf_service.resolve_public_official_pdf_url(stored_value=plan.official_pdf_key)
    if official_pdf_url is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Official PDF not found")
    return FlightPlanOfficialPdfUrlResponse(official_pdf_url=official_pdf_url)


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

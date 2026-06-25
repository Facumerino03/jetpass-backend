from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.models.user import Role
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.repositories.validation_criterion_repository import ValidationCriterionRepository
from app.repositories.validation_block_repository import ValidationBlockRepository
from app.schemas.validation import (
    ValidationBlockCreate,
    ValidationBlockPublic,
    ValidationBlockUpdate,
    ValidationCriterionCreate,
    ValidationCriterionPublic,
    ValidationCriterionUpdate,
    ValidationRunRequest,
    ValidationRunResponse,
)
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/validation", tags=["validation"])


def _block_to_dict(block) -> dict:
    criteria = [
        ValidationCriterionPublic.model_validate(link.criterion)
        for link in block.block_criteria
        if link.criterion and link.criterion.is_active
    ]
    return {
        "id": str(block.id),
        "created_by_user_id": str(block.created_by_user_id),
        "name": block.name,
        "is_active": block.is_active,
        "criteria": [c.model_dump() for c in criteria],
        "criteria_count": len(criteria),
    }


@router.get("/fields")
async def list_available_fields() -> list[dict]:
    from app.icao.fpl_mapping import FPL_FIELD_MAP

    return [
        {"field_path": field_path, "item": info["item"], "label": info["label"]}
        for field_path, info in FPL_FIELD_MAP.items()
    ]


def _ensure_authority_or_admin(current_user) -> None:
    if current_user.role not in {Role.ADMIN, Role.ATC_AUTHORITY}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and authorities can manage validation criteria",
        )


@router.get("/criteria")
async def list_criteria(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[ValidationCriterionPublic]:
    criteria = await ValidationCriterionRepository.list_active_by_user(db, user_id=current_user.id)
    return [ValidationCriterionPublic.model_validate(c) for c in criteria]


@router.post("/criteria", status_code=status.HTTP_201_CREATED)
async def create_criterion(
    payload: ValidationCriterionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ValidationCriterionPublic:
    _ensure_authority_or_admin(current_user)
    criterion = await ValidationCriterionRepository.create(
        db,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    await db.commit()
    await db.refresh(criterion)
    return ValidationCriterionPublic.model_validate(criterion)


@router.patch("/criteria/{criterion_id}")
async def update_criterion(
    criterion_id: UUID,
    payload: ValidationCriterionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ValidationCriterionPublic:
    _ensure_authority_or_admin(current_user)
    criterion = await ValidationCriterionRepository.get_by_id(db, criterion_id=criterion_id)
    if criterion is None or criterion.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Criterion not found")
    await ValidationCriterionRepository.update(criterion, **payload.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(criterion)
    return ValidationCriterionPublic.model_validate(criterion)


@router.delete("/criteria/{criterion_id}")
async def delete_criterion(
    criterion_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> dict:
    _ensure_authority_or_admin(current_user)
    criterion = await ValidationCriterionRepository.get_by_id(db, criterion_id=criterion_id)
    if criterion is None or criterion.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Criterion not found")
    await ValidationCriterionRepository.soft_delete(criterion)
    await db.commit()
    return {"ok": True}


@router.get("/blocks")
async def list_blocks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[dict]:
    blocks = await ValidationBlockRepository.list_active_by_user(db, user_id=current_user.id)
    return [_block_to_dict(b) for b in blocks]


@router.post("/blocks", status_code=status.HTTP_201_CREATED)
async def create_block(
    payload: ValidationBlockCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> dict:
    _ensure_authority_or_admin(current_user)
    block = await ValidationBlockRepository.create(
        db,
        created_by_user_id=current_user.id,
        name=payload.name,
        criterion_ids=payload.criterion_ids,
    )
    await db.commit()
    block = await ValidationBlockRepository.get_by_id(db, block_id=block.id)
    return _block_to_dict(block)


@router.patch("/blocks/{block_id}")
async def update_block(
    block_id: UUID,
    payload: ValidationBlockUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> dict:
    _ensure_authority_or_admin(current_user)
    block = await ValidationBlockRepository.get_by_id(db, block_id=block_id)
    if block is None or block.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    if payload.name is not None:
        await ValidationBlockRepository.update(block, name=payload.name)
    if payload.criterion_ids is not None:
        await ValidationBlockRepository.update_criteria(db, block, criterion_ids=payload.criterion_ids)
    await db.commit()
    await db.refresh(block)
    return _block_to_dict(block)


@router.delete("/blocks/{block_id}")
async def delete_block(
    block_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> dict:
    _ensure_authority_or_admin(current_user)
    block = await ValidationBlockRepository.get_by_id(db, block_id=block_id)
    if block is None or block.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    await ValidationBlockRepository.soft_delete(block)
    await db.commit()
    return {"ok": True}


@router.post("/run")
async def run_validation(
    payload: ValidationRunRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> ValidationRunResponse:
    _ensure_authority_or_admin(current_user)
    plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=payload.flight_plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")

    if payload.block_id is not None:
        block = await ValidationBlockRepository.get_by_id(db, block_id=payload.block_id)
        if block is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
        criterion_ids = [link.criterion_id for link in block.block_criteria if link.criterion and link.criterion.is_active]
    else:
        criterion_ids = payload.criterion_ids or []

    criteria = await ValidationCriterionRepository.get_active_by_ids(db, ids=criterion_ids)
    return ValidationService.evaluate(plan, criteria)

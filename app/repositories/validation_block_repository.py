from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.validation_block import ValidationBlock, ValidationBlockCriterion


class ValidationBlockRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        created_by_user_id: UUID,
        name: str,
        criterion_ids: list[UUID],
    ) -> ValidationBlock:
        block = ValidationBlock(created_by_user_id=created_by_user_id, name=name)
        db.add(block)
        await db.flush()
        for idx, cid in enumerate(criterion_ids):
            link = ValidationBlockCriterion(block_id=block.id, criterion_id=cid, order=idx)
            db.add(link)
        await db.flush()
        return block

    @staticmethod
    async def get_by_id(db: AsyncSession, *, block_id: UUID) -> ValidationBlock | None:
        result = await db.execute(
            select(ValidationBlock)
            .options(
                selectinload(ValidationBlock.block_criteria).options(joinedload(ValidationBlockCriterion.criterion))
            )
            .where(ValidationBlock.id == block_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_by_user(db: AsyncSession, *, user_id: UUID) -> list[ValidationBlock]:
        result = await db.execute(
            select(ValidationBlock)
            .options(
                selectinload(ValidationBlock.block_criteria).options(joinedload(ValidationBlockCriterion.criterion))
            )
            .where(
                ValidationBlock.created_by_user_id == user_id,
                ValidationBlock.is_active.is_(True),
            )
            .order_by(ValidationBlock.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_criteria(db: AsyncSession, block: ValidationBlock, *, criterion_ids: list[UUID]) -> ValidationBlock:
        for link in block.block_criteria:
            await db.delete(link)
        await db.flush()
        for idx, cid in enumerate(criterion_ids):
            db.add(ValidationBlockCriterion(block_id=block.id, criterion_id=cid, order=idx))
        await db.flush()
        return block

    @staticmethod
    async def update(block: ValidationBlock, **fields) -> ValidationBlock:
        for key, value in fields.items():
            setattr(block, key, value)
        return block

    @staticmethod
    async def soft_delete(block: ValidationBlock) -> ValidationBlock:
        block.is_active = False
        return block

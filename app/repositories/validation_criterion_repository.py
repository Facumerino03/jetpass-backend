from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.validation_criterion import CriterionOperator, CriterionResult, ValidationCriterion


class ValidationCriterionRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        created_by_user_id: UUID,
        name: str,
        field_path: str,
        operator: CriterionOperator,
        expected_value: str | None,
        result_on_pass: CriterionResult,
        result_on_fail: CriterionResult,
        pass_message: str | None = None,
        fail_message: str | None = None,
    ) -> ValidationCriterion:
        criterion = ValidationCriterion(
            created_by_user_id=created_by_user_id,
            name=name,
            field_path=field_path,
            operator=operator,
            expected_value=expected_value,
            result_on_pass=result_on_pass,
            result_on_fail=result_on_fail,
            pass_message=pass_message,
            fail_message=fail_message,
        )
        db.add(criterion)
        await db.flush()
        return criterion

    @staticmethod
    async def get_by_id(db: AsyncSession, *, criterion_id: UUID) -> ValidationCriterion | None:
        result = await db.execute(
            select(ValidationCriterion).where(ValidationCriterion.id == criterion_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_by_user(db: AsyncSession, *, user_id: UUID) -> list[ValidationCriterion]:
        result = await db.execute(
            select(ValidationCriterion)
            .where(
                ValidationCriterion.created_by_user_id == user_id,
                ValidationCriterion.is_active.is_(True),
            )
            .order_by(ValidationCriterion.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_by_ids(db: AsyncSession, *, ids: list[UUID]) -> list[ValidationCriterion]:
        result = await db.execute(
            select(ValidationCriterion).where(
                ValidationCriterion.id.in_(ids),
                ValidationCriterion.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(criterion: ValidationCriterion, **fields) -> ValidationCriterion:
        for key, value in fields.items():
            setattr(criterion, key, value)
        return criterion

    @staticmethod
    async def soft_delete(criterion: ValidationCriterion) -> ValidationCriterion:
        criterion.is_active = False
        return criterion

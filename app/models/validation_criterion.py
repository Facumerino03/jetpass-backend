from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CriterionOperator(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IS_PRESENT = "is_present"
    IS_ABSENT = "is_absent"


class CriterionResult(StrEnum):
    APPROVE = "approve"
    WARN = "warn"
    REJECT = "reject"


class ValidationCriterion(Base):
    __tablename__ = "validation_criteria"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    field_path: Mapped[str] = mapped_column(String(200), nullable=False)
    operator: Mapped[CriterionOperator] = mapped_column(
        Enum(CriterionOperator, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
    )
    expected_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_on_pass: Mapped[CriterionResult] = mapped_column(
        Enum(CriterionResult, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
    )
    result_on_fail: Mapped[CriterionResult] = mapped_column(
        Enum(CriterionResult, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
    )
    pass_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

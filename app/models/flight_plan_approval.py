from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FlightPlanApprovalActor(StrEnum):
    PILOT = "pilot"
    AUTHORITY = "authority"
    DESTINATION_AERODROME_OPERATOR = "destination_aerodrome_operator"


class FlightPlanApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FlightPlanApproval(Base):
    __tablename__ = "flight_plan_approvals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    flight_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("flight_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    actor: Mapped[FlightPlanApprovalActor] = mapped_column(
        Enum(FlightPlanApprovalActor, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
        index=True,
    )
    criterion: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[FlightPlanApprovalStatus] = mapped_column(
        Enum(FlightPlanApprovalStatus, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
        default=FlightPlanApprovalStatus.PENDING,
        index=True,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejected_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flight_plan = relationship("FlightPlan", back_populates="approvals")

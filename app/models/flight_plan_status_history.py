from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.flight_plan import FlightPlanStatus


class FlightPlanStatusHistory(Base):
    __tablename__ = "flight_plan_status_history"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    flight_plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("flight_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[FlightPlanStatus | None] = mapped_column(
        Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]),
        nullable=True,
    )
    to_status: Mapped[FlightPlanStatus] = mapped_column(
        Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    flight_plan = relationship("FlightPlan", back_populates="status_history")

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WakeTurbulenceCat(StrEnum):
    L = "L"
    M = "M"
    H = "H"
    J = "J"


class Aircraft(Base):
    __tablename__ = "aircraft"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identification: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    icao_type_designator: Mapped[str] = mapped_column(String(10), nullable=False)
    wake_turbulence_category: Mapped[WakeTurbulenceCat] = mapped_column(
        Enum(WakeTurbulenceCat),
        nullable=False,
    )
    equipment_com_nav: Mapped[str] = mapped_column(String(80), nullable=False)
    equipment_surveillance: Mapped[str] = mapped_column(String(80), nullable=False)
    pbn_capabilities: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emergency_radio_uhf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_radio_vhf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_radio_elt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_equipment_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_polar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_desert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_maritime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_jungle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_lights: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_fluorescein: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_uhf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_vhf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_cover_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color_and_markings: Mapped[str] = mapped_column(String(255), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
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

    owner = relationship("User", back_populates="aircraft")
    flight_plans = relationship("FlightPlan", back_populates="aircraft")

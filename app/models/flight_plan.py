from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.aircraft import WakeTurbulenceCat


class FlightRules(StrEnum):
    V = "V"
    I = "I"
    Y = "Y"
    Z = "Z"


class FlightType(StrEnum):
    G = "G"
    S = "S"
    N = "N"
    M = "M"
    X = "X"


class FlightPlanStatus(StrEnum):
    DRAFT = "draft"
    FILED = "filed"
    PENDING_APPROVAL = "pending_approval"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ACTIVE = "active"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class FlightPlan(Base):
    __tablename__ = "flight_plans"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    pilot_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    aircraft_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True)
    status: Mapped[FlightPlanStatus] = mapped_column(
        Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
        default=FlightPlanStatus.DRAFT,
        index=True,
    )

    aircraft_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    flight_rules: Mapped[FlightRules | None] = mapped_column(
        Enum(FlightRules, values_callable=lambda obj: [item.value for item in obj]),
        nullable=True,
    )
    flight_type: Mapped[FlightType | None] = mapped_column(
        Enum(FlightType, values_callable=lambda obj: [item.value for item in obj]),
        nullable=True,
    )
    departure_aerodrome_icao: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    departure_time_utc: Mapped[str | None] = mapped_column(String(4), nullable=True)
    flight_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    destination_aerodrome_icao: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    alternate1_aerodrome_icao: Mapped[str] = mapped_column(String(16), nullable=False)
    alternate2_aerodrome_icao: Mapped[str] = mapped_column(String(16), nullable=False)
    cruising_speed: Mapped[str | None] = mapped_column(String(5), nullable=True)
    cruising_level: Mapped[str | None] = mapped_column(String(5), nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_eet: Mapped[str | None] = mapped_column(String(4), nullable=True)
    other_information: Mapped[str | None] = mapped_column(Text, nullable=True)
    endurance: Mapped[str | None] = mapped_column(String(4), nullable=True)
    persons_on_board: Mapped[int | None] = mapped_column(Integer, nullable=True)

    aircraft_identification_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aircraft_type_designator_snapshot: Mapped[str | None] = mapped_column(String(10), nullable=True)
    wake_turbulence_category_snapshot: Mapped[WakeTurbulenceCat | None] = mapped_column(Enum(WakeTurbulenceCat), nullable=True)
    equipment_com_nav_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    equipment_surveillance_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emergency_radio_uhf_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_radio_vhf_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emergency_radio_elt_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_equipment_present_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_polar_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_desert_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_maritime_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    survival_jungle_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_present_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_lights_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_fluorescein_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_uhf_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    life_jackets_vhf_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_present_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_number_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_capacity_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_cover_present_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dinghies_color_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color_and_markings_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aircraft_snapshot_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    remarks_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    pilot_in_command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    official_pdf_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pilot = relationship("User", back_populates="flight_plans")
    aircraft = relationship("Aircraft", back_populates="flight_plans")
    approvals = relationship("FlightPlanApproval", back_populates="flight_plan", cascade="all, delete-orphan")
    status_history = relationship("FlightPlanStatusHistory", back_populates="flight_plan", cascade="all, delete-orphan")

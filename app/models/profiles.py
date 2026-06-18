from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuthorityType(StrEnum):
    ARO = "ARO"
    AIS = "AIS"
    ACC = "ACC"
    APP = "APP"
    TWR = "TWR"
    EANA = "EANA"
    ANAC = "ANAC"


class PilotProfile(Base):
    __tablename__ = "pilot_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    license_number: Mapped[str] = mapped_column(String(80), nullable=False)
    license_type: Mapped[str] = mapped_column(String(40), nullable=False)
    license_country: Mapped[str] = mapped_column(String(2), nullable=False)
    license_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="pilot_profile")


class AuthorityProfile(Base):
    __tablename__ = "authority_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    organization_name: Mapped[str] = mapped_column(String(160), nullable=False)
    authority_type: Mapped[AuthorityType] = mapped_column(
        Enum(AuthorityType, values_callable=lambda obj: [item.value for item in obj]),
        nullable=False,
    )
    aerodrome_icao_code: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="authority_profile")


class AirportOperatorProfile(Base):
    __tablename__ = "airport_operator_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    organization_name: Mapped[str] = mapped_column(String(160), nullable=False)
    aerodrome_icao_code: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="airport_operator_profile")

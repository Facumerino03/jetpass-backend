# Flight Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the flight-plan MVP described in `docs/superpowers/specs/2026-05-18-flight-plan-design.md` with wizard drafts, aircraft snapshots, manual approvals, profiles, and intelligence proxy endpoints.

**Architecture:** Follow the existing FastAPI MVC-style backend: SQLAlchemy async models, repository query classes, service-layer business rules, Pydantic schemas, route handlers, and async pytest coverage. Reuse existing `User`, `Role`, `Aircraft`, and `AircraftRepository`; do not duplicate user or aircraft models.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, Alembic, httpx, pytest, pytest-asyncio, aiosqlite test database.

**Commit Policy:** Do not run `git commit` during execution unless the user explicitly asks for commits. Each task still includes a verification checkpoint.

---

## Scope And File Map

Create:

- `app/models/profiles.py`: pilot, authority, and airport-operator profile ORM models plus `AuthorityType`.
- `app/models/flight_plan.py`: flight-plan ORM model and flight-plan enums.
- `app/models/flight_plan_approval.py`: persisted manual approval ORM model and approval enums.
- `app/models/flight_plan_status_history.py`: status transition history ORM model.
- `app/repositories/profile_repository.py`: profile create/get helpers for services and tests.
- `app/repositories/flight_plan_repository.py`: plan persistence, ownership/visibility queries, and list helpers.
- `app/repositories/flight_plan_approval_repository.py`: approval persistence and pending approval queries.
- `app/repositories/flight_plan_status_history_repository.py`: status-history persistence and reads.
- `app/schemas/flight_plan.py`: request/response schemas for plan creation, patching, submit, approve/reject, and public payloads.
- `app/schemas/intelligence.py`: schemas for plan-oriented intelligence proxy requests/responses.
- `app/services/flight_plan_validations.py`: pure validation helpers for ICAO codes, HHMM parsing, endurance comparison, and route rule-change validation.
- `app/services/flight_plan_service.py`: wizard, ownership, snapshot, submit, state, and approval business logic.
- `app/services/intelligence_client.py`: httpx adapter for `jetpass-intelligence`.
- `app/routes/flight_plans.py`: `/flight-plans` routes.
- `app/tests/test_profiles_repositories.py`: repository tests for profiles.
- `app/tests/test_flight_plan_validations.py`: pure validation tests.
- `app/tests/test_flight_plan_repositories.py`: repository tests for plans, approvals, and history.
- `app/tests/test_flight_plan_service.py`: service tests for wizard, snapshot, submit, approvals.
- `app/tests/test_flight_plans.py`: route tests.
- `app/tests/test_flight_plan_intelligence.py`: intelligence proxy tests.
- `alembic/versions/<generated>_add_flight_plan_tables.py`: migration for profiles, flight plans, approvals, and history.

Modify:

- `app/models/user.py`: add profile and flight-plan relationships.
- `app/models/aircraft.py`: add optional `flight_plans` relationship.
- `app/models/__init__.py`: import new model modules if needed for test metadata discovery.
- `app/core/config.py`: add `INTELLIGENCE_BASE_URL` and `INTELLIGENCE_TIMEOUT_SECONDS`.
- `app/main.py`: include `flight_plans.router`.

---

### Task 1: Profile Models And Repository

**Files:**

- Create: `app/models/profiles.py`
- Create: `app/repositories/profile_repository.py`
- Modify: `app/models/user.py`
- Modify: `app/models/__init__.py`
- Test: `app/tests/test_profiles_repositories.py`

- [ ] **Step 1: Write failing profile repository tests**

Create `app/tests/test_profiles_repositories.py`:

```python
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.profiles import AuthorityType
from app.models.user import Role
from app.repositories.profile_repository import ProfileRepository
from app.repositories.user_repository import UserRepository


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(db_session, *, email: str, role: Role):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        phone=None,
        role=role,
    )


@pytest.mark.asyncio
async def test_profile_repository_creates_and_fetches_authority_profile(db_session):
    user = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)

    profile = await ProfileRepository.create_authority_profile(
        db_session,
        user_id=user.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_authority_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.user_id == user.id
    assert fetched.organization_name == "ANAC"
    assert fetched.authority_type == AuthorityType.ANAC
    assert fetched.aerodrome_icao_code is None


@pytest.mark.asyncio
async def test_profile_repository_normalizes_airport_operator_aerodrome(db_session):
    user = await create_user(db_session, email="operator@example.com", role=Role.AIRPORT_OPERATOR)

    profile = await ProfileRepository.create_airport_operator_profile(
        db_session,
        user_id=user.id,
        organization_name="Ezeiza Operator",
        aerodrome_icao_code="saez",
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_airport_operator_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.aerodrome_icao_code == "SAEZ"


@pytest.mark.asyncio
async def test_profile_repository_creates_pilot_profile(db_session):
    user = await create_user(db_session, email="pilot-profile@example.com", role=Role.PILOT)

    profile = await ProfileRepository.create_pilot_profile(
        db_session,
        user_id=user.id,
        license_number="PPA-123",
        license_type="PPA",
        license_country="AR",
        license_expiry=date(2030, 1, 1),
        signature="Amelia Earhart",
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_pilot_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.license_number == "PPA-123"
```

- [ ] **Step 2: Run profile tests to verify failure**

Run: `pytest app/tests/test_profiles_repositories.py -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `app.models.profiles` or `app.repositories.profile_repository`.

- [ ] **Step 3: Add profile ORM models**

Create `app/models/profiles.py`:

```python
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
```

- [ ] **Step 4: Add user relationships**

Modify `app/models/user.py` by adding these relationships after the existing `aircraft` relationship:

```python
    pilot_profile = relationship(
        "PilotProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    authority_profile = relationship(
        "AuthorityProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    airport_operator_profile = relationship(
        "AirportOperatorProfile",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
```

Update `app/models/__init__.py` so tests can import all new models:

```python
from app.models import aircraft, auth_session, profiles, user

__all__ = ["aircraft", "auth_session", "profiles", "user"]
```

- [ ] **Step 5: Add profile repository**

Create `app/repositories/profile_repository.py`:

```python
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import AirportOperatorProfile, AuthorityProfile, AuthorityType, PilotProfile


class ProfileRepository:
    @staticmethod
    async def create_pilot_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        license_number: str,
        license_type: str,
        license_country: str,
        license_expiry: date,
        signature: str | None,
    ) -> PilotProfile:
        profile = PilotProfile(
            user_id=user_id,
            license_number=license_number,
            license_type=license_type,
            license_country=license_country.upper(),
            license_expiry=license_expiry,
            signature=signature,
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_pilot_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> PilotProfile | None:
        result = await db.execute(select(PilotProfile).where(PilotProfile.user_id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_authority_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        organization_name: str,
        authority_type: AuthorityType,
        aerodrome_icao_code: str | None,
    ) -> AuthorityProfile:
        profile = AuthorityProfile(
            user_id=user_id,
            organization_name=organization_name,
            authority_type=authority_type,
            aerodrome_icao_code=aerodrome_icao_code.upper() if aerodrome_icao_code else None,
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_authority_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> AuthorityProfile | None:
        result = await db.execute(select(AuthorityProfile).where(AuthorityProfile.user_id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_airport_operator_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        organization_name: str,
        aerodrome_icao_code: str,
    ) -> AirportOperatorProfile:
        profile = AirportOperatorProfile(
            user_id=user_id,
            organization_name=organization_name,
            aerodrome_icao_code=aerodrome_icao_code.upper(),
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_airport_operator_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> AirportOperatorProfile | None:
        result = await db.execute(select(AirportOperatorProfile).where(AirportOperatorProfile.user_id == user_id))
        return result.scalar_one_or_none()
```

- [ ] **Step 6: Run profile tests**

Run: `pytest app/tests/test_profiles_repositories.py -v`

Expected: PASS.

---

### Task 2: Flight Plan Models And Repository

**Files:**

- Create: `app/models/flight_plan.py`
- Create: `app/models/flight_plan_approval.py`
- Create: `app/models/flight_plan_status_history.py`
- Create: `app/repositories/flight_plan_repository.py`
- Create: `app/repositories/flight_plan_approval_repository.py`
- Create: `app/repositories/flight_plan_status_history_repository.py`
- Modify: `app/models/user.py`
- Modify: `app/models/aircraft.py`
- Modify: `app/models/__init__.py`
- Test: `app/tests/test_flight_plan_repositories.py`

- [ ] **Step 1: Write failing flight-plan repository tests**

Create `app/tests/test_flight_plan_repositories.py`:

```python
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.flight_plan import FlightPlanStatus
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.models.user import Role
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository
from app.repositories.user_repository import UserRepository


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_pilot(db_session, *, email: str = "pilot@example.com"):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
    )


@pytest.mark.asyncio
async def test_flight_plan_repository_creates_step_one_draft(db_session):
    pilot = await create_pilot(db_session)
    eobt = datetime(2026, 5, 18, 14, 30, tzinfo=timezone.utc)

    plan = await FlightPlanRepository.create_draft(
        db_session,
        pilot_user_id=pilot.id,
        departure_aerodrome_icao="sabe",
        departure_eobt_utc=eobt,
        destination_aerodrome_icao="saez",
        alternate1_aerodrome_icao="sadp",
        alternate2_aerodrome_icao="sadf",
    )
    await db_session.commit()

    fetched = await FlightPlanRepository.get_by_id(db_session, flight_plan_id=plan.id)

    assert fetched is not None
    assert fetched.id == plan.id
    assert fetched.status == FlightPlanStatus.DRAFT
    assert fetched.pilot_user_id == pilot.id
    assert fetched.departure_aerodrome_icao == "SABE"
    assert fetched.destination_aerodrome_icao == "SAEZ"
    assert fetched.alternate1_aerodrome_icao == "SADP"
    assert fetched.alternate2_aerodrome_icao == "SADF"


@pytest.mark.asyncio
async def test_approval_and_history_repositories_persist_records(db_session):
    pilot = await create_pilot(db_session)
    plan = await FlightPlanRepository.create_draft(
        db_session,
        pilot_user_id=pilot.id,
        departure_aerodrome_icao="SABE",
        departure_eobt_utc=datetime(2026, 5, 18, 14, 30, tzinfo=timezone.utc),
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
    )

    history = await FlightPlanStatusHistoryRepository.create(
        db_session,
        flight_plan_id=plan.id,
        from_status=FlightPlanStatus.DRAFT,
        to_status=FlightPlanStatus.FILED,
        updated_by_user_id=pilot.id,
        reason="submitted",
    )
    approval = await FlightPlanApprovalRepository.create(
        db_session,
        flight_plan_id=plan.id,
        actor=FlightPlanApprovalActor.PILOT,
        criterion="pilot_submission",
        status=FlightPlanApprovalStatus.APPROVED,
        approved_by_user_id=pilot.id,
    )
    await db_session.commit()

    histories = await FlightPlanStatusHistoryRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    approvals = await FlightPlanApprovalRepository.list_by_plan(db_session, flight_plan_id=plan.id)

    assert [item.id for item in histories] == [history.id]
    assert [item.id for item in approvals] == [approval.id]
    assert approvals[0].criterion == "pilot_submission"
    assert approvals[0].status == FlightPlanApprovalStatus.APPROVED
```

- [ ] **Step 2: Run repository tests to verify failure**

Run: `pytest app/tests/test_flight_plan_repositories.py -v`

Expected: FAIL with missing model/repository imports.

- [ ] **Step 3: Add flight-plan ORM model**

Create `app/models/flight_plan.py`:

```python
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
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
    status: Mapped[FlightPlanStatus] = mapped_column(Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]), nullable=False, default=FlightPlanStatus.DRAFT, index=True)

    flight_rules: Mapped[FlightRules | None] = mapped_column(Enum(FlightRules, values_callable=lambda obj: [item.value for item in obj]), nullable=True)
    flight_type: Mapped[FlightType | None] = mapped_column(Enum(FlightType, values_callable=lambda obj: [item.value for item in obj]), nullable=True)
    departure_aerodrome_icao: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    departure_eobt_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    destination_aerodrome_icao: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    alternate1_aerodrome_icao: Mapped[str] = mapped_column(String(4), nullable=False)
    alternate2_aerodrome_icao: Mapped[str] = mapped_column(String(4), nullable=False)
    cruising_speed: Mapped[str | None] = mapped_column(String(5), nullable=True)
    cruising_level: Mapped[str | None] = mapped_column(String(5), nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_change_point: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_eet: Mapped[str | None] = mapped_column(String(4), nullable=True)
    other_information: Mapped[str | None] = mapped_column(Text, nullable=True)
    endurance: Mapped[str | None] = mapped_column(String(4), nullable=True)
    persons_on_board: Mapped[int | None] = mapped_column(Integer, nullable=True)

    aircraft_identification_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aircraft_type_designator_snapshot: Mapped[str | None] = mapped_column(String(10), nullable=True)
    wake_turbulence_category_snapshot: Mapped[WakeTurbulenceCat | None] = mapped_column(Enum(WakeTurbulenceCat), nullable=True)
    equipment_com_nav_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    equipment_surveillance_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emergency_radio_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    survival_equipment_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    life_jackets_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dinghies_number_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_capacity_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_cover_snapshot: Mapped[bool | None] = mapped_column(nullable=True)
    dinghies_color_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color_and_markings_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aircraft_snapshot_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pilot = relationship("User", back_populates="flight_plans")
    aircraft = relationship("Aircraft", back_populates="flight_plans")
    approvals = relationship("FlightPlanApproval", back_populates="flight_plan", cascade="all, delete-orphan")
    status_history = relationship("FlightPlanStatusHistory", back_populates="flight_plan", cascade="all, delete-orphan")
```

- [ ] **Step 4: Add approval and history models**

Create `app/models/flight_plan_approval.py`:

```python
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
    actor: Mapped[FlightPlanApprovalActor] = mapped_column(Enum(FlightPlanApprovalActor, values_callable=lambda obj: [item.value for item in obj]), nullable=False, index=True)
    criterion: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[FlightPlanApprovalStatus] = mapped_column(Enum(FlightPlanApprovalStatus, values_callable=lambda obj: [item.value for item in obj]), nullable=False, default=FlightPlanApprovalStatus.PENDING, index=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejected_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flight_plan = relationship("FlightPlan", back_populates="approvals")
```

Create `app/models/flight_plan_status_history.py`:

```python
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
    from_status: Mapped[FlightPlanStatus | None] = mapped_column(Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]), nullable=True)
    to_status: Mapped[FlightPlanStatus] = mapped_column(Enum(FlightPlanStatus, values_callable=lambda obj: [item.value for item in obj]), nullable=False)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    flight_plan = relationship("FlightPlan", back_populates="status_history")
```

- [ ] **Step 5: Add relationships and model imports**

Modify `app/models/user.py` by adding:

```python
    flight_plans = relationship(
        "FlightPlan",
        back_populates="pilot",
        cascade="all, delete-orphan",
    )
```

Modify `app/models/aircraft.py` by adding:

```python
    flight_plans = relationship("FlightPlan", back_populates="aircraft")
```

Update `app/models/__init__.py`:

```python
from app.models import aircraft, auth_session, flight_plan, flight_plan_approval, flight_plan_status_history, profiles, user

__all__ = [
    "aircraft",
    "auth_session",
    "flight_plan",
    "flight_plan_approval",
    "flight_plan_status_history",
    "profiles",
    "user",
]
```

- [ ] **Step 6: Add repositories**

Create `app/repositories/flight_plan_repository.py`:

```python
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan import FlightPlan, FlightPlanStatus


class FlightPlanRepository:
    @staticmethod
    async def create_draft(
        db: AsyncSession,
        *,
        pilot_user_id: UUID,
        departure_aerodrome_icao: str,
        departure_eobt_utc: datetime,
        destination_aerodrome_icao: str,
        alternate1_aerodrome_icao: str,
        alternate2_aerodrome_icao: str,
    ) -> FlightPlan:
        plan = FlightPlan(
            pilot_user_id=pilot_user_id,
            status=FlightPlanStatus.DRAFT,
            departure_aerodrome_icao=departure_aerodrome_icao.upper(),
            departure_eobt_utc=departure_eobt_utc,
            destination_aerodrome_icao=destination_aerodrome_icao.upper(),
            alternate1_aerodrome_icao=alternate1_aerodrome_icao.upper(),
            alternate2_aerodrome_icao=alternate2_aerodrome_icao.upper(),
        )
        db.add(plan)
        await db.flush()
        return plan

    @staticmethod
    async def get_by_id(db: AsyncSession, *, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(select(FlightPlan).where(FlightPlan.id == flight_plan_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_owner_and_id(db: AsyncSession, *, pilot_user_id: UUID, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(
            select(FlightPlan).where(
                FlightPlan.id == flight_plan_id,
                FlightPlan.pilot_user_id == pilot_user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_pilot(db: AsyncSession, *, pilot_user_id: UUID) -> list[FlightPlan]:
        result = await db.execute(
            select(FlightPlan)
            .where(FlightPlan.pilot_user_id == pilot_user_id)
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all(db: AsyncSession) -> list[FlightPlan]:
        result = await db.execute(select(FlightPlan).order_by(FlightPlan.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def update(plan: FlightPlan, **fields: Any) -> FlightPlan:
        uppercase_fields = {
            "departure_aerodrome_icao",
            "destination_aerodrome_icao",
            "alternate1_aerodrome_icao",
            "alternate2_aerodrome_icao",
            "cruising_speed",
            "cruising_level",
            "rule_change_point",
            "aircraft_identification_snapshot",
            "aircraft_type_designator_snapshot",
            "equipment_com_nav_snapshot",
            "equipment_surveillance_snapshot",
        }
        for key, value in fields.items():
            if key in uppercase_fields and isinstance(value, str):
                value = value.upper()
            setattr(plan, key, value)
        return plan
```

Create `app/repositories/flight_plan_approval_repository.py`:

```python
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan_approval import FlightPlanApproval, FlightPlanApprovalActor, FlightPlanApprovalStatus


class FlightPlanApprovalRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        actor: FlightPlanApprovalActor,
        criterion: str,
        status: FlightPlanApprovalStatus = FlightPlanApprovalStatus.PENDING,
        approved_by_user_id: UUID | None = None,
    ) -> FlightPlanApproval:
        approval = FlightPlanApproval(
            flight_plan_id=flight_plan_id,
            actor=actor,
            criterion=criterion,
            status=status,
            approved_by_user_id=approved_by_user_id,
            decided_at=datetime.now(timezone.utc) if status == FlightPlanApprovalStatus.APPROVED else None,
        )
        db.add(approval)
        await db.flush()
        return approval

    @staticmethod
    async def list_by_plan(db: AsyncSession, *, flight_plan_id: UUID) -> list[FlightPlanApproval]:
        result = await db.execute(
            select(FlightPlanApproval)
            .where(FlightPlanApproval.flight_plan_id == flight_plan_id)
            .order_by(FlightPlanApproval.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_pending_by_actor(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        actor: FlightPlanApprovalActor,
    ) -> FlightPlanApproval | None:
        result = await db.execute(
            select(FlightPlanApproval).where(
                FlightPlanApproval.flight_plan_id == flight_plan_id,
                FlightPlanApproval.actor == actor,
                FlightPlanApproval.status == FlightPlanApprovalStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_approved(approval: FlightPlanApproval, *, approved_by_user_id: UUID) -> FlightPlanApproval:
        approval.status = FlightPlanApprovalStatus.APPROVED
        approval.approved_by_user_id = approved_by_user_id
        approval.rejected_by_user_id = None
        approval.reason = None
        approval.decided_at = datetime.now(timezone.utc)
        return approval

    @staticmethod
    async def mark_rejected(approval: FlightPlanApproval, *, rejected_by_user_id: UUID, reason: str) -> FlightPlanApproval:
        approval.status = FlightPlanApprovalStatus.REJECTED
        approval.rejected_by_user_id = rejected_by_user_id
        approval.approved_by_user_id = None
        approval.reason = reason
        approval.decided_at = datetime.now(timezone.utc)
        return approval
```

Create `app/repositories/flight_plan_status_history_repository.py`:

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan import FlightPlanStatus
from app.models.flight_plan_status_history import FlightPlanStatusHistory


class FlightPlanStatusHistoryRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        from_status: FlightPlanStatus | None,
        to_status: FlightPlanStatus,
        updated_by_user_id: UUID | None,
        reason: str | None,
    ) -> FlightPlanStatusHistory:
        history = FlightPlanStatusHistory(
            flight_plan_id=flight_plan_id,
            from_status=from_status,
            to_status=to_status,
            updated_by_user_id=updated_by_user_id,
            reason=reason,
        )
        db.add(history)
        await db.flush()
        return history

    @staticmethod
    async def list_by_plan(db: AsyncSession, *, flight_plan_id: UUID) -> list[FlightPlanStatusHistory]:
        result = await db.execute(
            select(FlightPlanStatusHistory)
            .where(FlightPlanStatusHistory.flight_plan_id == flight_plan_id)
            .order_by(FlightPlanStatusHistory.created_at.asc())
        )
        return list(result.scalars().all())
```

- [ ] **Step 7: Run flight-plan repository tests**

Run: `pytest app/tests/test_flight_plan_repositories.py -v`

Expected: PASS.

---

### Task 3: Flight Plan Validation Helpers

**Files:**

- Create: `app/services/flight_plan_validations.py`
- Test: `app/tests/test_flight_plan_validations.py`

- [ ] **Step 1: Write failing validation tests**

Create `app/tests/test_flight_plan_validations.py`:

```python
import pytest

from app.services.flight_plan_validations import (
    ensure_all_aerodromes_distinct,
    ensure_rule_change_point_valid,
    ensure_valid_icao_code,
    hhmm_to_minutes,
)


def test_ensure_valid_icao_code_normalizes_uppercase():
    assert ensure_valid_icao_code("saez") == "SAEZ"


def test_ensure_valid_icao_code_rejects_invalid_length():
    with pytest.raises(ValueError, match="ICAO code must be 4 alphanumeric characters"):
        ensure_valid_icao_code("SAE")


def test_ensure_all_aerodromes_distinct_rejects_duplicates():
    with pytest.raises(ValueError, match="Aerodrome codes must be distinct"):
        ensure_all_aerodromes_distinct("SABE", "SAEZ", "SADP", "SAEZ")


def test_hhmm_to_minutes_parses_time_duration():
    assert hhmm_to_minutes("0130") == 90


def test_hhmm_to_minutes_rejects_bad_minutes():
    with pytest.raises(ValueError, match="HHMM minutes must be between 00 and 59"):
        hhmm_to_minutes("0160")


def test_rule_change_point_required_for_y_or_z_and_must_appear_in_route():
    ensure_rule_change_point_valid("Y", "DCT GUALE DCT", "GUALE")
    with pytest.raises(ValueError, match="rule_change_point is required"):
        ensure_rule_change_point_valid("Z", "DCT GUALE DCT", None)
    with pytest.raises(ValueError, match="rule_change_point must appear in route"):
        ensure_rule_change_point_valid("Y", "DCT GUALE DCT", "PAL")
```

- [ ] **Step 2: Run validation tests to verify failure**

Run: `pytest app/tests/test_flight_plan_validations.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Add validation helpers**

Create `app/services/flight_plan_validations.py`:

```python
import re


_ICAO_RE = re.compile(r"^[A-Z0-9]{4}$")
_HHMM_RE = re.compile(r"^[0-9]{4}$")


def ensure_valid_icao_code(value: str) -> str:
    normalized = value.upper()
    if not _ICAO_RE.fullmatch(normalized):
        raise ValueError("ICAO code must be 4 alphanumeric characters")
    return normalized


def ensure_all_aerodromes_distinct(*codes: str) -> None:
    normalized = [ensure_valid_icao_code(code) for code in codes]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Aerodrome codes must be distinct")


def hhmm_to_minutes(value: str) -> int:
    if not _HHMM_RE.fullmatch(value):
        raise ValueError("HHMM value must contain exactly 4 digits")
    hours = int(value[:2])
    minutes = int(value[2:])
    if minutes > 59:
        raise ValueError("HHMM minutes must be between 00 and 59")
    return hours * 60 + minutes


def ensure_rule_change_point_valid(flight_rules: str, route: str | None, rule_change_point: str | None) -> None:
    if flight_rules not in {"Y", "Z"}:
        return
    if not rule_change_point:
        raise ValueError("rule_change_point is required for Y/Z flight rules")
    if not route or rule_change_point.upper() not in route.upper().split():
        raise ValueError("rule_change_point must appear in route")
```

- [ ] **Step 4: Run validation tests**

Run: `pytest app/tests/test_flight_plan_validations.py -v`

Expected: PASS.

---

### Task 4: Flight Plan Schemas And Service Draft Flow

**Files:**

- Create: `app/schemas/flight_plan.py`
- Create: `app/services/flight_plan_service.py`
- Test: `app/tests/test_flight_plan_service.py`

- [ ] **Step 1: Write failing service tests for create, patch, and snapshot**

Create `app/tests/test_flight_plan_service.py` with initial draft-flow tests:

```python
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlanStatus
from app.models.user import Role
from app.repositories.aircraft_repository import AircraftRepository
from app.repositories.user_repository import UserRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanUpdate
from app.services.flight_plan_service import FlightPlanService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(db_session, *, email: str, role: Role):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=role,
    )


async def create_aircraft(db_session, pilot):
    return await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Trainer",
        identification="lv-abc",
        icao_type_designator="c172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFGR",
        equipment_surveillance="B1",
        pbn_capabilities="B2C2D2",
        emergency_radio="UVE",
        survival_equipment="J",
        life_jackets="L",
        dinghies_number=1,
        dinghies_capacity=4,
        dinghies_cover=True,
        dinghies_color="Orange",
        color_and_markings="White with blue stripes",
    )


def create_payload():
    return FlightPlanCreate(
        departure_aerodrome_icao="sabe",
        departure_eobt_utc=datetime(2026, 5, 18, 14, 30, tzinfo=timezone.utc),
        destination_aerodrome_icao="saez",
        alternate1_aerodrome_icao="sadp",
        alternate2_aerodrome_icao="sadf",
    )


@pytest.mark.asyncio
async def test_service_creates_step_one_draft_for_pilot(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)

    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())

    assert plan.status == FlightPlanStatus.DRAFT
    assert plan.pilot_user_id == pilot.id
    assert plan.departure_aerodrome_icao == "SABE"


@pytest.mark.asyncio
async def test_service_rejects_duplicate_aerodromes(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    payload = FlightPlanCreate(
        departure_aerodrome_icao="SABE",
        departure_eobt_utc=datetime(2026, 5, 18, 14, 30, tzinfo=timezone.utc),
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SAEZ",
    )

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.create_draft(db_session, pilot, payload)

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_service_selects_aircraft_and_generates_snapshot(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())

    updated = await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(aircraft_id=aircraft.id),
    )

    assert updated.aircraft_id == aircraft.id
    assert updated.aircraft_identification_snapshot == "LV-ABC"
    assert updated.aircraft_type_designator_snapshot == "C172"
    assert updated.equipment_com_nav_snapshot == "SDFGR"
    assert updated.aircraft_snapshot_confirmed_at is not None


@pytest.mark.asyncio
async def test_service_rejects_aircraft_owned_by_another_pilot(db_session):
    owner = await create_user(db_session, email="owner@example.com", role=Role.PILOT)
    other = await create_user(db_session, email="other@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, owner)
    plan = await FlightPlanService.create_draft(db_session, other, create_payload())

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.update_draft(
            db_session,
            other,
            plan.id,
            FlightPlanUpdate(aircraft_id=aircraft.id),
        )

    assert exc.value.status_code == 404
```

- [ ] **Step 2: Run service tests to verify failure**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: FAIL with missing schemas/service.

- [ ] **Step 3: Add flight-plan schemas**

Create `app/schemas/flight_plan.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlanStatus, FlightRules, FlightType
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.services.flight_plan_validations import ensure_valid_icao_code


class FlightPlanCreate(BaseModel):
    departure_aerodrome_icao: str = Field(min_length=4, max_length=4)
    departure_eobt_utc: datetime
    destination_aerodrome_icao: str = Field(min_length=4, max_length=4)
    alternate1_aerodrome_icao: str = Field(min_length=4, max_length=4)
    alternate2_aerodrome_icao: str = Field(min_length=4, max_length=4)

    @field_validator("departure_aerodrome_icao", "destination_aerodrome_icao", "alternate1_aerodrome_icao", "alternate2_aerodrome_icao")
    @classmethod
    def normalize_icao(cls, value: str) -> str:
        return ensure_valid_icao_code(value)


class FlightPlanUpdate(BaseModel):
    flight_rules: FlightRules | None = None
    flight_type: FlightType | None = None
    aircraft_id: UUID | None = None
    aircraft_identification_snapshot: str | None = Field(default=None, min_length=1, max_length=20)
    aircraft_type_designator_snapshot: str | None = Field(default=None, min_length=1, max_length=10)
    wake_turbulence_category_snapshot: WakeTurbulenceCat | None = None
    equipment_com_nav_snapshot: str | None = Field(default=None, min_length=1, max_length=80)
    equipment_surveillance_snapshot: str | None = Field(default=None, min_length=1, max_length=80)
    emergency_radio_snapshot: str | None = Field(default=None, max_length=20)
    survival_equipment_snapshot: str | None = Field(default=None, max_length=20)
    life_jackets_snapshot: str | None = Field(default=None, max_length=20)
    dinghies_number_snapshot: int | None = Field(default=None, ge=0)
    dinghies_capacity_snapshot: int | None = Field(default=None, ge=0)
    dinghies_cover_snapshot: bool | None = None
    dinghies_color_snapshot: str | None = Field(default=None, max_length=40)
    color_and_markings_snapshot: str | None = Field(default=None, min_length=1, max_length=255)
    cruising_speed: str | None = Field(default=None, min_length=1, max_length=5)
    cruising_level: str | None = Field(default=None, min_length=1, max_length=5)
    route: str | None = Field(default=None, min_length=1)
    rule_change_point: str | None = Field(default=None, max_length=40)
    total_eet: str | None = Field(default=None, min_length=4, max_length=4)
    other_information: str | None = None
    endurance: str | None = Field(default=None, min_length=4, max_length=4)
    persons_on_board: int | None = Field(default=None, ge=1)


class FlightPlanSubmitResponse(BaseModel):
    id: UUID
    status: FlightPlanStatus


class FlightPlanDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class FlightPlanApprovalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor: FlightPlanApprovalActor
    criterion: str
    status: FlightPlanApprovalStatus
    approved_by_user_id: UUID | None
    rejected_by_user_id: UUID | None
    reason: str | None
    decided_at: datetime | None


class FlightPlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pilot_user_id: UUID
    aircraft_id: UUID | None
    status: FlightPlanStatus
    flight_rules: FlightRules | None
    flight_type: FlightType | None
    departure_aerodrome_icao: str
    departure_eobt_utc: datetime
    destination_aerodrome_icao: str
    alternate1_aerodrome_icao: str
    alternate2_aerodrome_icao: str
    cruising_speed: str | None
    cruising_level: str | None
    route: str | None
    rule_change_point: str | None
    total_eet: str | None
    other_information: str | None
    endurance: str | None
    persons_on_board: int | None
    aircraft_identification_snapshot: str | None
    aircraft_type_designator_snapshot: str | None
    wake_turbulence_category_snapshot: WakeTurbulenceCat | None
    equipment_com_nav_snapshot: str | None
    equipment_surveillance_snapshot: str | None
    emergency_radio_snapshot: str | None
    survival_equipment_snapshot: str | None
    life_jackets_snapshot: str | None
    dinghies_number_snapshot: int | None
    dinghies_capacity_snapshot: int | None
    dinghies_cover_snapshot: bool | None
    dinghies_color_snapshot: str | None
    color_and_markings_snapshot: str | None
    aircraft_snapshot_confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FlightPlanStatusHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_status: FlightPlanStatus | None
    to_status: FlightPlanStatus
    updated_by_user_id: UUID | None
    reason: str | None
    created_at: datetime


class FlightPlanDetailPublic(FlightPlanPublic):
    approvals: list[FlightPlanApprovalPublic] = Field(default_factory=list)
    status_history: list[FlightPlanStatusHistoryPublic] = Field(default_factory=list)
```

- [ ] **Step 4: Add draft service methods**

Create `app/services/flight_plan_service.py` with initial draft logic:

```python
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft
from app.models.flight_plan import FlightPlan, FlightPlanStatus
from app.models.user import Role, User
from app.repositories.aircraft_repository import AircraftRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanUpdate
from app.services.flight_plan_validations import ensure_all_aerodromes_distinct


class FlightPlanService:
    @staticmethod
    def _ensure_pilot(current_user: User) -> None:
        if current_user.role != Role.PILOT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only pilots can manage flight plans")

    @staticmethod
    def _ensure_draft(plan: FlightPlan) -> None:
        if plan.status != FlightPlanStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Flight plan can only be edited in draft status")

    @staticmethod
    async def create_draft(db: AsyncSession, current_user: User, payload: FlightPlanCreate) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        try:
            ensure_all_aerodromes_distinct(
                payload.departure_aerodrome_icao,
                payload.destination_aerodrome_icao,
                payload.alternate1_aerodrome_icao,
                payload.alternate2_aerodrome_icao,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        plan = await FlightPlanRepository.create_draft(
            db,
            pilot_user_id=current_user.id,
            departure_aerodrome_icao=payload.departure_aerodrome_icao,
            departure_eobt_utc=payload.departure_eobt_utc,
            destination_aerodrome_icao=payload.destination_aerodrome_icao,
            alternate1_aerodrome_icao=payload.alternate1_aerodrome_icao,
            alternate2_aerodrome_icao=payload.alternate2_aerodrome_icao,
        )
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    def _snapshot_from_aircraft(aircraft: Aircraft) -> dict:
        return {
            "aircraft_identification_snapshot": aircraft.identification,
            "aircraft_type_designator_snapshot": aircraft.icao_type_designator,
            "wake_turbulence_category_snapshot": aircraft.wake_turbulence_category,
            "equipment_com_nav_snapshot": aircraft.equipment_com_nav,
            "equipment_surveillance_snapshot": aircraft.equipment_surveillance,
            "emergency_radio_snapshot": aircraft.emergency_radio,
            "survival_equipment_snapshot": aircraft.survival_equipment,
            "life_jackets_snapshot": aircraft.life_jackets,
            "dinghies_number_snapshot": aircraft.dinghies_number,
            "dinghies_capacity_snapshot": aircraft.dinghies_capacity,
            "dinghies_cover_snapshot": aircraft.dinghies_cover,
            "dinghies_color_snapshot": aircraft.dinghies_color,
            "color_and_markings_snapshot": aircraft.color_and_markings,
            "aircraft_snapshot_confirmed_at": datetime.now(timezone.utc),
        }

    @staticmethod
    async def update_draft(
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
        payload: FlightPlanUpdate,
    ) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)

        fields = payload.model_dump(exclude_unset=True)
        aircraft_id = fields.pop("aircraft_id", None)
        if aircraft_id is not None:
            aircraft = await AircraftRepository.get_active_by_owner_and_id(db, owner_user_id=current_user.id, aircraft_id=aircraft_id)
            if aircraft is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
            fields["aircraft_id"] = aircraft.id
            fields.update(FlightPlanService._snapshot_from_aircraft(aircraft))

        await FlightPlanRepository.update(plan, **fields)
        await db.commit()
        await db.refresh(plan)
        return plan
```

- [ ] **Step 5: Run service draft tests**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: PASS for the tests currently in the file.

---

### Task 5: Submit And Approval Service Logic

**Files:**

- Modify: `app/services/flight_plan_service.py`
- Modify: `app/tests/test_flight_plan_service.py`

- [ ] **Step 1: Add failing submit and approval tests**

Append to `app/tests/test_flight_plan_service.py`:

```python
from app.models.flight_plan_approval import FlightPlanApprovalStatus
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository


async def complete_plan(db_session, pilot):
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())
    return await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(
            flight_rules="V",
            flight_type="G",
            aircraft_id=aircraft.id,
            cruising_speed="N0120",
            cruising_level="A045",
            route="DCT GUALE DCT",
            total_eet="0100",
            endurance="0230",
            persons_on_board=2,
            other_information="RMK/TRAINING",
        ),
    )


@pytest.mark.asyncio
async def test_submit_complete_plan_creates_history_and_approvals(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    plan = await complete_plan(db_session, pilot)

    submitted = await FlightPlanService.submit(db_session, pilot, plan.id)

    assert submitted.status == FlightPlanStatus.PENDING_APPROVAL
    histories = await FlightPlanStatusHistoryRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    approvals = await FlightPlanApprovalRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    assert [(item.from_status, item.to_status) for item in histories] == [
        (FlightPlanStatus.DRAFT, FlightPlanStatus.FILED),
        (FlightPlanStatus.FILED, FlightPlanStatus.PENDING_APPROVAL),
    ]
    assert [item.criterion for item in approvals] == [
        "pilot_submission",
        "authority_acceptance",
        "destination_aerodrome_acceptance",
    ]
    assert approvals[0].status == FlightPlanApprovalStatus.APPROVED
    assert approvals[1].status == FlightPlanApprovalStatus.PENDING
    assert approvals[2].status == FlightPlanApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_submit_requires_endurance_greater_than_total_eet(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())
    plan = await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(
            flight_rules="V",
            flight_type="G",
            aircraft_id=aircraft.id,
            cruising_speed="N0120",
            cruising_level="A045",
            route="DCT GUALE DCT",
            total_eet="0200",
            endurance="0130",
            persons_on_board=2,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.submit(db_session, pilot, plan.id)

    assert exc.value.status_code == 422
    assert "endurance must be greater than total_eet" in exc.value.detail


@pytest.mark.asyncio
async def test_submit_requires_rule_change_point_for_y_rules(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())
    plan = await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(
            flight_rules="Y",
            flight_type="G",
            aircraft_id=aircraft.id,
            cruising_speed="N0120",
            cruising_level="A045",
            route="DCT GUALE DCT",
            total_eet="0100",
            endurance="0230",
            persons_on_board=2,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.submit(db_session, pilot, plan.id)

    assert exc.value.status_code == 422
    assert "rule_change_point is required" in exc.value.detail
```

- [ ] **Step 2: Run submit tests to verify failure**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: FAIL with `AttributeError` for missing `FlightPlanService.submit`.

- [ ] **Step 3: Implement submit logic**

Modify `app/services/flight_plan_service.py` imports:

```python
from app.models.flight_plan import FlightPlan, FlightPlanStatus, FlightRules
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository
from app.services.flight_plan_validations import ensure_all_aerodromes_distinct, ensure_rule_change_point_valid, hhmm_to_minutes
```

Add methods inside `FlightPlanService`:

```python
    @staticmethod
    def _validate_complete_for_submit(plan: FlightPlan) -> None:
        missing = []
        required_fields = [
            "flight_rules",
            "flight_type",
            "aircraft_id",
            "aircraft_identification_snapshot",
            "aircraft_type_designator_snapshot",
            "wake_turbulence_category_snapshot",
            "equipment_com_nav_snapshot",
            "equipment_surveillance_snapshot",
            "color_and_markings_snapshot",
            "aircraft_snapshot_confirmed_at",
            "cruising_speed",
            "cruising_level",
            "route",
            "total_eet",
            "endurance",
            "persons_on_board",
        ]
        for field in required_fields:
            if getattr(plan, field) in {None, ""}:
                missing.append(field)
        if missing:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required fields: {', '.join(missing)}")

        if plan.persons_on_board is None or plan.persons_on_board < 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="persons_on_board must be at least 1")

        try:
            if hhmm_to_minutes(plan.endurance) <= hhmm_to_minutes(plan.total_eet):
                raise ValueError("endurance must be greater than total_eet")
            ensure_rule_change_point_valid(str(plan.flight_rules.value), plan.route, plan.rule_change_point)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    @staticmethod
    async def _transition(
        db: AsyncSession,
        plan: FlightPlan,
        *,
        to_status: FlightPlanStatus,
        updated_by_user_id: UUID,
        reason: str,
    ) -> None:
        from_status = plan.status
        plan.status = to_status
        await FlightPlanStatusHistoryRepository.create(
            db,
            flight_plan_id=plan.id,
            from_status=from_status,
            to_status=to_status,
            updated_by_user_id=updated_by_user_id,
            reason=reason,
        )

    @staticmethod
    async def submit(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)
        FlightPlanService._validate_complete_for_submit(plan)

        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.FILED, updated_by_user_id=current_user.id, reason="submitted")
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.PILOT,
            criterion="pilot_submission",
            status=FlightPlanApprovalStatus.APPROVED,
            approved_by_user_id=current_user.id,
        )
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.AUTHORITY,
            criterion="authority_acceptance",
        )
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR,
            criterion="destination_aerodrome_acceptance",
        )
        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.PENDING_APPROVAL, updated_by_user_id=current_user.id, reason="awaiting manual approvals")
        await db.commit()
        await db.refresh(plan)
        return plan
```

- [ ] **Step 4: Run submit tests**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: PASS.

---

### Task 6: Manual Approval Policy

**Files:**

- Modify: `app/services/flight_plan_service.py`
- Modify: `app/tests/test_flight_plan_service.py`

- [ ] **Step 1: Add failing approval policy tests**

Append to `app/tests/test_flight_plan_service.py`:

```python
from app.models.profiles import AuthorityType
from app.repositories.profile_repository import ProfileRepository


@pytest.mark.asyncio
async def test_authority_and_airport_operator_approval_accepts_plan(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    authority = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)
    operator = await create_user(db_session, email="operator@example.com", role=Role.AIRPORT_OPERATOR)
    await ProfileRepository.create_authority_profile(
        db_session,
        user_id=authority.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    await ProfileRepository.create_airport_operator_profile(
        db_session,
        user_id=operator.id,
        organization_name="Ezeiza Operator",
        aerodrome_icao_code="SAEZ",
    )
    plan = await complete_plan(db_session, pilot)
    plan = await FlightPlanService.submit(db_session, pilot, plan.id)

    plan = await FlightPlanService.approve(db_session, authority, plan.id)
    assert plan.status == FlightPlanStatus.PENDING_APPROVAL

    plan = await FlightPlanService.approve(db_session, operator, plan.id)
    assert plan.status == FlightPlanStatus.ACCEPTED


@pytest.mark.asyncio
async def test_reject_requires_reason_and_transitions_plan_to_rejected(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    authority = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)
    await ProfileRepository.create_authority_profile(
        db_session,
        user_id=authority.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    plan = await complete_plan(db_session, pilot)
    plan = await FlightPlanService.submit(db_session, pilot, plan.id)

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.reject(db_session, authority, plan.id, reason="")
    assert exc.value.status_code == 422

    rejected = await FlightPlanService.reject(db_session, authority, plan.id, reason="Route requires correction")
    assert rejected.status == FlightPlanStatus.REJECTED
```

- [ ] **Step 2: Run approval tests to verify failure**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: FAIL with missing `approve` or `reject`.

- [ ] **Step 3: Implement approval policy**

Modify `app/services/flight_plan_service.py` imports:

```python
from app.models.profiles import AuthorityType
from app.repositories.profile_repository import ProfileRepository
```

Add methods inside `FlightPlanService`:

```python
    @staticmethod
    async def _approval_actor_for_user(db: AsyncSession, current_user: User, plan: FlightPlan) -> FlightPlanApprovalActor:
        if current_user.role == Role.ADMIN:
            authority = await FlightPlanApprovalRepository.get_pending_by_actor(db, flight_plan_id=plan.id, actor=FlightPlanApprovalActor.AUTHORITY)
            if authority is not None:
                return FlightPlanApprovalActor.AUTHORITY
            return FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR

        if current_user.role == Role.ATC_AUTHORITY:
            profile = await ProfileRepository.get_authority_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authority profile is required")
            if profile.authority_type in {AuthorityType.ANAC, AuthorityType.EANA}:
                return FlightPlanApprovalActor.AUTHORITY
            relevant = {
                plan.departure_aerodrome_icao,
                plan.destination_aerodrome_icao,
                plan.alternate1_aerodrome_icao,
                plan.alternate2_aerodrome_icao,
            }
            if profile.aerodrome_icao_code in relevant:
                return FlightPlanApprovalActor.AUTHORITY
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authority profile does not apply to this flight plan")

        if current_user.role == Role.AIRPORT_OPERATOR:
            profile = await ProfileRepository.get_airport_operator_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Airport operator profile is required")
            if profile.aerodrome_icao_code != plan.destination_aerodrome_icao:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Airport operator profile does not match destination aerodrome")
            return FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot approve flight plans")

    @staticmethod
    async def _get_pending_decision(db: AsyncSession, current_user: User, plan: FlightPlan):
        if plan.status != FlightPlanStatus.PENDING_APPROVAL:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Flight plan is not pending approval")
        actor = await FlightPlanService._approval_actor_for_user(db, current_user, plan)
        approval = await FlightPlanApprovalRepository.get_pending_by_actor(db, flight_plan_id=plan.id, actor=actor)
        if approval is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending approval not found")
        return approval

    @staticmethod
    async def approve(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        approval = await FlightPlanService._get_pending_decision(db, current_user, plan)
        await FlightPlanApprovalRepository.mark_approved(approval, approved_by_user_id=current_user.id)
        approvals = await FlightPlanApprovalRepository.list_by_plan(db, flight_plan_id=plan.id)
        if all(item.status == FlightPlanApprovalStatus.APPROVED for item in approvals):
            await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.ACCEPTED, updated_by_user_id=current_user.id, reason="all approvals completed")
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    async def reject(db: AsyncSession, current_user: User, flight_plan_id: UUID, *, reason: str) -> FlightPlan:
        if not reason.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection reason is required")
        plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        approval = await FlightPlanService._get_pending_decision(db, current_user, plan)
        await FlightPlanApprovalRepository.mark_rejected(approval, rejected_by_user_id=current_user.id, reason=reason.strip())
        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.REJECTED, updated_by_user_id=current_user.id, reason=reason.strip())
        await db.commit()
        await db.refresh(plan)
        return plan
```

- [ ] **Step 4: Run approval service tests**

Run: `pytest app/tests/test_flight_plan_service.py -v`

Expected: PASS.

---

### Task 7: Flight Plan Routes

**Files:**

- Create: `app/routes/flight_plans.py`
- Modify: `app/main.py`
- Test: `app/tests/test_flight_plans.py`

- [ ] **Step 1: Write failing route tests**

Create `app/tests/test_flight_plans.py`:

```python
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import aircraft as _aircraft_model
from app.models import auth_session as _auth_session_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    await engine.dispose()


async def register_pilot(client: AsyncClient, email: str = "pilot@example.com") -> str:
    response = await client.post(
        "/auth/register/pilot",
        json={"email": email, "password": "safe-password-123", "first_name": "Amelia", "last_name": "Earhart", "phone": None},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def step_one_payload() -> dict:
    return {
        "departure_aerodrome_icao": "sabe",
        "departure_eobt_utc": "2026-05-18T14:30:00Z",
        "destination_aerodrome_icao": "saez",
        "alternate1_aerodrome_icao": "sadp",
        "alternate2_aerodrome_icao": "sadf",
    }


@pytest.mark.asyncio
async def test_pilot_can_create_list_get_and_patch_draft_flight_plan(client):
    token = await register_pilot(client)
    headers = auth_headers(token)

    create_response = await client.post("/flight-plans", json=step_one_payload(), headers=headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "draft"
    assert created["departure_aerodrome_icao"] == "SABE"
    flight_plan_id = created["id"]

    list_response = await client.get("/flight-plans", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [flight_plan_id]

    get_response = await client.get(f"/flight-plans/{flight_plan_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == flight_plan_id

    patch_response = await client.patch(
        f"/flight-plans/{flight_plan_id}",
        json={"flight_rules": "V", "flight_type": "G"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["flight_rules"] == "V"


@pytest.mark.asyncio
async def test_flight_plan_routes_require_authentication(client):
    response = await client.post("/flight-plans", json=step_one_payload())
    assert response.status_code == 401
```

- [ ] **Step 2: Run route tests to verify failure**

Run: `pytest app/tests/test_flight_plans.py -v`

Expected: FAIL with 404 for `/flight-plans`.

- [ ] **Step 3: Add route module**

Create `app/routes/flight_plans.py`:

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.models.user import Role
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanDecisionRequest, FlightPlanDetailPublic, FlightPlanPublic, FlightPlanSubmitResponse, FlightPlanUpdate
from app.services.flight_plan_service import FlightPlanService

router = APIRouter(prefix="/flight-plans", tags=["flight-plans"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flight_plan(
    payload: FlightPlanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.create_draft(db, current_user, payload)
    return FlightPlanPublic.model_validate(plan)


@router.get("")
async def list_flight_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[FlightPlanPublic]:
    plans = await FlightPlanService.list_visible(db, current_user)
    return [FlightPlanPublic.model_validate(plan) for plan in plans]


@router.get("/{flight_plan_id}")
async def get_flight_plan(
    flight_plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanDetailPublic:
    plan = await FlightPlanService.get_visible(db, current_user, flight_plan_id)
    return FlightPlanDetailPublic.model_validate(plan)


@router.patch("/{flight_plan_id}")
async def update_flight_plan(
    flight_plan_id: UUID,
    payload: FlightPlanUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> FlightPlanPublic:
    plan = await FlightPlanService.update_draft(db, current_user, flight_plan_id, payload)
    return FlightPlanPublic.model_validate(plan)


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
```

- [ ] **Step 4: Add list-visible and get-visible service methods**

Add these imports to `app/repositories/flight_plan_repository.py`:

```python
from app.models.flight_plan import FlightPlan, FlightPlanStatus
from sqlalchemy.orm import selectinload
```

Update `get_by_id` and `get_by_owner_and_id` so detail responses can serialize approvals and status history without async lazy-loading errors:

```python
    @staticmethod
    async def get_by_id(db: AsyncSession, *, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(
            select(FlightPlan)
            .options(selectinload(FlightPlan.approvals), selectinload(FlightPlan.status_history))
            .where(FlightPlan.id == flight_plan_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_owner_and_id(db: AsyncSession, *, pilot_user_id: UUID, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(
            select(FlightPlan)
            .options(selectinload(FlightPlan.approvals), selectinload(FlightPlan.status_history))
            .where(
                FlightPlan.id == flight_plan_id,
                FlightPlan.pilot_user_id == pilot_user_id,
            )
        )
        return result.scalar_one_or_none()
```

Add these methods to `FlightPlanRepository`:

```python
    @staticmethod
    async def list_pending_for_destination(db: AsyncSession, *, destination_aerodrome_icao: str) -> list[FlightPlan]:
        result = await db.execute(
            select(FlightPlan)
            .where(
                FlightPlan.destination_aerodrome_icao == destination_aerodrome_icao.upper(),
                FlightPlan.status == FlightPlanStatus.PENDING_APPROVAL,
            )
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_pending_for_relevant_aerodrome(db: AsyncSession, *, aerodrome_icao: str) -> list[FlightPlan]:
        code = aerodrome_icao.upper()
        result = await db.execute(
            select(FlightPlan)
            .where(
                FlightPlan.status == FlightPlanStatus.PENDING_APPROVAL,
                (
                    (FlightPlan.departure_aerodrome_icao == code)
                    | (FlightPlan.destination_aerodrome_icao == code)
                    | (FlightPlan.alternate1_aerodrome_icao == code)
                    | (FlightPlan.alternate2_aerodrome_icao == code)
                ),
            )
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())
```

Add to `FlightPlanService`:

```python
    @staticmethod
    async def list_visible(db: AsyncSession, current_user: User) -> list[FlightPlan]:
        if current_user.role == Role.ADMIN:
            return await FlightPlanRepository.list_all(db)
        if current_user.role == Role.PILOT:
            return await FlightPlanRepository.list_by_pilot(db, pilot_user_id=current_user.id)
        if current_user.role == Role.AIRPORT_OPERATOR:
            profile = await ProfileRepository.get_airport_operator_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                return []
            return await FlightPlanRepository.list_pending_for_destination(
                db,
                destination_aerodrome_icao=profile.aerodrome_icao_code,
            )
        if current_user.role == Role.ATC_AUTHORITY:
            profile = await ProfileRepository.get_authority_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                return []
            if profile.authority_type in {AuthorityType.ANAC, AuthorityType.EANA}:
                return [plan for plan in await FlightPlanRepository.list_all(db) if plan.status == FlightPlanStatus.PENDING_APPROVAL]
            if profile.aerodrome_icao_code is None:
                return []
            return await FlightPlanRepository.list_pending_for_relevant_aerodrome(
                db,
                aerodrome_icao=profile.aerodrome_icao_code,
            )
        return []

    @staticmethod
    async def get_visible(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        if current_user.role == Role.ADMIN:
            plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        elif current_user.role == Role.PILOT:
            plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        else:
            plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        return plan
```

- [ ] **Step 5: Include router in app**

Modify `app/main.py` imports:

```python
from app.routes import aircraft, auth, flight_plans, health
```

Add router include in `create_app`:

```python
    application.include_router(flight_plans.router)
```

- [ ] **Step 6: Run route tests**

Run: `pytest app/tests/test_flight_plans.py -v`

Expected: PASS.

---

### Task 8: Intelligence Proxy

**Files:**

- Modify: `app/core/config.py`
- Create: `app/schemas/intelligence.py`
- Create: `app/services/intelligence_client.py`
- Modify: `app/routes/flight_plans.py`
- Test: `app/tests/test_flight_plan_intelligence.py`

- [ ] **Step 1: Write failing intelligence client tests**

Create `app/tests/test_flight_plan_intelligence.py`:

```python
import httpx
import pytest

from app.services.intelligence_client import IntelligenceClient


@pytest.mark.asyncio
async def test_intelligence_client_posts_aerodrome_intent():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"intent": "aerodrome", "alerts": [], "metadata": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://intelligence") as http_client:
        client = IntelligenceClient(base_url="http://intelligence", timeout_seconds=1.0, http_client=http_client)
        response = await client.run({"aerodrome": {"icao": "SAEZ", "force_refresh": False}})

    assert response["intent"] == "aerodrome"
    assert requests[0].url.path == "/intelligence/run"
    assert requests[0].read() == b'{"aerodrome":{"icao":"SAEZ","force_refresh":false}}'


@pytest.mark.asyncio
async def test_intelligence_client_returns_unavailable_payload_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://intelligence") as http_client:
        client = IntelligenceClient(base_url="http://intelligence", timeout_seconds=1.0, http_client=http_client)
        response = await client.run({"notam": {"icao": "SAEZ", "force_refresh": False}})

    assert response["intent"] == "unavailable"
    assert response["alerts"] == [
        {"level": "warning", "code": "INTELLIGENCE_UNAVAILABLE", "message": "Aeronautical intelligence is unavailable"}
    ]
```

- [ ] **Step 2: Run intelligence tests to verify failure**

Run: `pytest app/tests/test_flight_plan_intelligence.py -v`

Expected: FAIL with missing module.

- [ ] **Step 3: Add config fields**

Modify `app/core/config.py` by adding fields to `Settings`:

```python
    INTELLIGENCE_BASE_URL: str | None = None
    INTELLIGENCE_TIMEOUT_SECONDS: float = 5.0
```

- [ ] **Step 4: Add intelligence schemas**

Create `app/schemas/intelligence.py`:

```python
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.services.flight_plan_validations import ensure_valid_icao_code


class IntelligenceAerodromeRequest(BaseModel):
    icao: str = Field(min_length=4, max_length=4)
    force_refresh: bool = False

    @field_validator("icao")
    @classmethod
    def normalize_icao(cls, value: str) -> str:
        return ensure_valid_icao_code(value)


class IntelligenceRunRequest(BaseModel):
    aerodrome: IntelligenceAerodromeRequest | None = None
    notam: IntelligenceAerodromeRequest | None = None


class IntelligenceRunResponse(BaseModel):
    intent: str
    aerodrome: dict[str, Any] | None = None
    notam: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
```

- [ ] **Step 5: Add intelligence client**

Create `app/services/intelligence_client.py`:

```python
from typing import Any

import httpx


class IntelligenceClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    @staticmethod
    def unavailable_response() -> dict[str, Any]:
        return {
            "intent": "unavailable",
            "aerodrome": None,
            "notam": None,
            "alerts": [
                {
                    "level": "warning",
                    "code": "INTELLIGENCE_UNAVAILABLE",
                    "message": "Aeronautical intelligence is unavailable",
                }
            ],
            "metadata": {},
        }

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            return self.unavailable_response()

        if self.http_client is not None:
            try:
                response = await self.http_client.post("/intelligence/run", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                return self.unavailable_response()

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.post("/intelligence/run", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError:
            return self.unavailable_response()
```

- [ ] **Step 6: Add intelligence routes**

Modify `app/routes/flight_plans.py` imports:

```python
from app.core.config import settings
from app.schemas.intelligence import IntelligenceAerodromeRequest, IntelligenceRunRequest, IntelligenceRunResponse
from app.services.intelligence_client import IntelligenceClient
```

Append routes before `/{flight_plan_id}` routes so static paths are not captured as UUIDs:

```python
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


@router.post("/intelligence/run")
async def flight_plan_run_intelligence(payload: IntelligenceRunRequest) -> IntelligenceRunResponse:
    client = IntelligenceClient(base_url=settings.INTELLIGENCE_BASE_URL, timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS)
    response = await client.run(payload.model_dump(exclude_none=True))
    return IntelligenceRunResponse.model_validate(response)
```

- [ ] **Step 7: Run intelligence tests**

Run: `pytest app/tests/test_flight_plan_intelligence.py -v`

Expected: PASS.

---

### Task 9: Alembic Migration

**Files:**

- Create: `alembic/versions/<revision>_add_flight_plan_tables.py`

- [ ] **Step 1: Verify Alembic can see metadata**

Run: `alembic revision --autogenerate -m "add flight plan tables"`

Expected: creates a new migration under `alembic/versions/`.

- [ ] **Step 2: Inspect generated migration**

Open the generated migration and verify it creates these tables:

- `pilot_profiles`
- `authority_profiles`
- `airport_operator_profiles`
- `flight_plans`
- `flight_plan_approvals`
- `flight_plan_status_history`

Expected: generated migration includes `op.create_table` calls for every table above and foreign keys to `users`, `aircraft`, and `flight_plans`.

- [ ] **Step 3: Fix migration imports and downgrade order if needed**

Ensure the migration has imports compatible with existing migrations:

```python
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
```

Ensure `downgrade()` drops child tables before parent tables:

```python
op.drop_table("flight_plan_status_history")
op.drop_table("flight_plan_approvals")
op.drop_table("flight_plans")
op.drop_table("airport_operator_profiles")
op.drop_table("authority_profiles")
op.drop_table("pilot_profiles")
```

- [ ] **Step 4: Run migration upgrade on configured dev database**

Run: `alembic upgrade head`

Expected: migration applies successfully. If no `DEV_DATABASE_URL` is configured, skip this command and rely on test metadata creation for local verification.

---

### Task 10: Full Verification And Cleanup

**Files:**

- Modify as needed based on failures from the commands below.

- [ ] **Step 1: Run focused test suite**

Run: `pytest app/tests/test_profiles_repositories.py app/tests/test_flight_plan_validations.py app/tests/test_flight_plan_repositories.py app/tests/test_flight_plan_service.py app/tests/test_flight_plans.py app/tests/test_flight_plan_intelligence.py -v`

Expected: PASS.

- [ ] **Step 2: Run all tests**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 3: Check app imports**

Run: `python -c "from app.main import app; print(app.title)"`

Expected: prints `Jetpass Backend Core`.

- [ ] **Step 4: Inspect git diff without committing**

Run: `git diff -- docs/superpowers/specs/2026-05-18-flight-plan-design.md docs/superpowers/plans/2026-05-18-flight-plan-implementation.md app alembic`

Expected: diff contains only flight-plan MVP changes and the approved spec/plan documents.

- [ ] **Step 5: Report completion**

Summarize:

- Files created and modified.
- Verification commands run and their results.
- Any skipped command and why it was skipped.
- Any follow-up work left outside MVP.

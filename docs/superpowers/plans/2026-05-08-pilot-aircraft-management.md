# Pilot Aircraft Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build authenticated pilot aircraft management with create, list, get, patch, and soft-delete endpoints.

**Architecture:** Follow the existing MVC-style FastAPI layout. SQLAlchemy models define persistence, repositories contain database queries, services enforce pilot ownership and role policy, schemas define API contracts, and routes expose `/pilot/aircraft` operations.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, pytest, httpx, aiosqlite for test database setup.

---

## Scope And File Map

Create:

- `app/models/aircraft.py`: `Aircraft` SQLAlchemy model and `WakeTurbulenceCat` enum.
- `app/schemas/aircraft.py`: request and response schemas for aircraft management.
- `app/repositories/aircraft_repository.py`: owner-scoped aircraft persistence methods.
- `app/services/aircraft_service.py`: role checks, ownership policy, and transaction orchestration.
- `app/routes/aircraft.py`: `/pilot/aircraft` FastAPI router.
- `app/tests/test_aircraft_repositories.py`: repository tests with async SQLite.
- `app/tests/test_aircraft.py`: endpoint tests with async SQLite and auth setup.

Modify:

- `app/models/user.py`: add `User.aircraft` relationship.
- `app/main.py`: include the aircraft router.

No database migration tooling exists in the repository. Tests use `Base.metadata.create_all`; runtime schema creation remains outside this feature.

Commit checkpoints are included for execution discipline, but in this repository do not run `git commit` unless the user explicitly authorizes commits during execution.

---

### Task 1: Aircraft Model And Repository

**Files:**

- Create: `app/models/aircraft.py`
- Modify: `app/models/user.py`
- Create: `app/repositories/aircraft_repository.py`
- Test: `app/tests/test_aircraft_repositories.py`

- [ ] **Step 1: Write failing repository tests**

Create `app/tests/test_aircraft_repositories.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models import aircraft as _aircraft_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.user import Role
from app.repositories.aircraft_repository import AircraftRepository
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


async def create_pilot(db_session, email="pilot@example.com"):
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
async def test_aircraft_repository_creates_and_fetches_active_aircraft_by_owner(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Club Cessna",
        identification="LV-ABC",
        icao_type_designator="C172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFG",
        equipment_surveillance="C",
        pbn_capabilities=None,
        emergency_radio=None,
        survival_equipment=None,
        life_jackets=None,
        dinghies_number=None,
        dinghies_capacity=None,
        dinghies_cover=None,
        dinghies_color=None,
        color_and_markings="White and blue",
    )
    await db_session.commit()

    fetched = await AircraftRepository.get_active_by_owner_and_id(
        db_session,
        owner_user_id=pilot.id,
        aircraft_id=aircraft.id,
    )
    aircraft_list = await AircraftRepository.list_active_by_owner(db_session, owner_user_id=pilot.id)

    assert fetched is not None
    assert fetched.id == aircraft.id
    assert fetched.owner_user_id == pilot.id
    assert fetched.is_active is True
    assert aircraft_list == [fetched]


@pytest.mark.asyncio
async def test_aircraft_repository_excludes_soft_deleted_aircraft(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias=None,
        identification="LV-DEF",
        icao_type_designator="PA28",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="S",
        equipment_surveillance="N",
        pbn_capabilities=None,
        emergency_radio=None,
        survival_equipment=None,
        life_jackets=None,
        dinghies_number=None,
        dinghies_capacity=None,
        dinghies_cover=None,
        dinghies_color=None,
        color_and_markings="Red",
    )

    await AircraftRepository.soft_delete(aircraft)
    await db_session.commit()

    fetched = await AircraftRepository.get_active_by_owner_and_id(
        db_session,
        owner_user_id=pilot.id,
        aircraft_id=aircraft.id,
    )
    aircraft_list = await AircraftRepository.list_active_by_owner(db_session, owner_user_id=pilot.id)

    assert fetched is None
    assert aircraft_list == []
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run: `pytest app/tests/test_aircraft_repositories.py -v`

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `app.models.aircraft` or `app.repositories.aircraft_repository`.

- [ ] **Step 3: Add the Aircraft model**

Create `app/models/aircraft.py`:

```python
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
    identification: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    icao_type_designator: Mapped[str] = mapped_column(String(10), nullable=False)
    wake_turbulence_category: Mapped[WakeTurbulenceCat] = mapped_column(Enum(WakeTurbulenceCat), nullable=False)
    equipment_com_nav: Mapped[str] = mapped_column(String(80), nullable=False)
    equipment_surveillance: Mapped[str] = mapped_column(String(80), nullable=False)
    pbn_capabilities: Mapped[str | None] = mapped_column(String(80), nullable=True)
    emergency_radio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    survival_equipment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    life_jackets: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dinghies_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dinghies_cover: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dinghies_color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color_and_markings: Mapped[str] = mapped_column(String(255), nullable=False)
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
```

- [ ] **Step 4: Add the User relationship**

Modify `app/models/user.py` by adding this relationship after `auth_sessions`:

```python
    aircraft = relationship(
        "Aircraft",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
```

- [ ] **Step 5: Add the repository**

Create `app/repositories/aircraft_repository.py`:

```python
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft, WakeTurbulenceCat


class AircraftRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        alias: str | None,
        identification: str,
        icao_type_designator: str,
        wake_turbulence_category: WakeTurbulenceCat,
        equipment_com_nav: str,
        equipment_surveillance: str,
        pbn_capabilities: str | None,
        emergency_radio: str | None,
        survival_equipment: str | None,
        life_jackets: str | None,
        dinghies_number: int | None,
        dinghies_capacity: int | None,
        dinghies_cover: bool | None,
        dinghies_color: str | None,
        color_and_markings: str,
    ) -> Aircraft:
        aircraft = Aircraft(
            owner_user_id=owner_user_id,
            alias=alias,
            identification=identification.upper(),
            icao_type_designator=icao_type_designator.upper(),
            wake_turbulence_category=wake_turbulence_category,
            equipment_com_nav=equipment_com_nav,
            equipment_surveillance=equipment_surveillance,
            pbn_capabilities=pbn_capabilities,
            emergency_radio=emergency_radio,
            survival_equipment=survival_equipment,
            life_jackets=life_jackets,
            dinghies_number=dinghies_number,
            dinghies_capacity=dinghies_capacity,
            dinghies_cover=dinghies_cover,
            dinghies_color=dinghies_color,
            color_and_markings=color_and_markings,
            is_active=True,
        )
        db.add(aircraft)
        await db.flush()
        return aircraft

    @staticmethod
    async def list_active_by_owner(db: AsyncSession, *, owner_user_id: UUID) -> list[Aircraft]:
        result = await db.execute(
            select(Aircraft)
            .where(Aircraft.owner_user_id == owner_user_id, Aircraft.is_active.is_(True))
            .order_by(Aircraft.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_by_owner_and_id(
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        aircraft_id: UUID,
    ) -> Aircraft | None:
        result = await db.execute(
            select(Aircraft).where(
                Aircraft.id == aircraft_id,
                Aircraft.owner_user_id == owner_user_id,
                Aircraft.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(aircraft: Aircraft, **fields: Any) -> Aircraft:
        for key, value in fields.items():
            if key in {"identification", "icao_type_designator"} and isinstance(value, str):
                value = value.upper()
            setattr(aircraft, key, value)
        return aircraft

    @staticmethod
    async def soft_delete(aircraft: Aircraft) -> Aircraft:
        aircraft.is_active = False
        return aircraft
```

- [ ] **Step 6: Run repository tests to verify they pass**

Run: `pytest app/tests/test_aircraft_repositories.py -v`

Expected: PASS for both repository tests.

- [ ] **Step 7: Commit checkpoint if authorized**

If the user explicitly authorized commits, run:

```bash
git add app/models/aircraft.py app/models/user.py app/repositories/aircraft_repository.py app/tests/test_aircraft_repositories.py
git commit -m "feat: add aircraft persistence"
```

---

### Task 2: Schemas And Service Policy

**Files:**

- Create: `app/schemas/aircraft.py`
- Create: `app/services/aircraft_service.py`
- Test: `app/tests/test_aircraft_service.py`

- [ ] **Step 1: Write failing service tests**

Create `app/tests/test_aircraft_service.py`:

```python
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models import aircraft as _aircraft_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.user import Role
from app.repositories.user_repository import UserRepository
from app.schemas.aircraft import AircraftCreate, AircraftUpdate
from app.services.aircraft_service import AircraftService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(db_session, email: str, role: Role):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=role,
    )


def aircraft_create_payload() -> AircraftCreate:
    return AircraftCreate(
        alias="Club Cessna",
        identification="lv-abc",
        icao_type_designator="c172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFG",
        equipment_surveillance="C",
        pbn_capabilities=None,
        emergency_radio=None,
        survival_equipment=None,
        life_jackets=None,
        dinghies_number=None,
        dinghies_capacity=None,
        dinghies_cover=None,
        dinghies_color=None,
        color_and_markings="White and blue",
    )


@pytest.mark.asyncio
async def test_aircraft_service_creates_updates_and_soft_deletes_for_pilot(db_session):
    pilot = await create_user(db_session, "pilot@example.com", Role.PILOT)

    aircraft = await AircraftService.create_for_pilot(db_session, current_user=pilot, payload=aircraft_create_payload())
    updated = await AircraftService.update_for_pilot(
        db_session,
        current_user=pilot,
        aircraft_id=aircraft.id,
        payload=AircraftUpdate(alias="Updated alias", color_and_markings="White"),
    )
    deleted = await AircraftService.delete_for_pilot(db_session, current_user=pilot, aircraft_id=aircraft.id)
    fetched_after_delete = await AircraftService.get_for_pilot(db_session, current_user=pilot, aircraft_id=aircraft.id)

    assert aircraft.owner_user_id == pilot.id
    assert aircraft.identification == "LV-ABC"
    assert updated.alias == "Updated alias"
    assert deleted is True
    assert fetched_after_delete is None


@pytest.mark.asyncio
async def test_aircraft_service_rejects_non_pilot_users(db_session):
    admin = await create_user(db_session, "admin@example.com", Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        await AircraftService.create_for_pilot(db_session, current_user=admin, payload=aircraft_create_payload())

    assert exc_info.value.status_code == 403
```

- [ ] **Step 2: Run service tests to verify they fail**

Run: `pytest app/tests/test_aircraft_service.py -v`

Expected: FAIL with `ModuleNotFoundError` for `app.schemas.aircraft` or `app.services.aircraft_service`.

- [ ] **Step 3: Add aircraft schemas**

Create `app/schemas/aircraft.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.aircraft import WakeTurbulenceCat


class AircraftCreate(BaseModel):
    alias: str | None = Field(default=None, max_length=120)
    identification: str = Field(min_length=1, max_length=20)
    icao_type_designator: str = Field(min_length=1, max_length=10)
    wake_turbulence_category: WakeTurbulenceCat
    equipment_com_nav: str = Field(min_length=1, max_length=80)
    equipment_surveillance: str = Field(min_length=1, max_length=80)
    pbn_capabilities: str | None = Field(default=None, max_length=80)
    emergency_radio: str | None = Field(default=None, max_length=20)
    survival_equipment: str | None = Field(default=None, max_length=20)
    life_jackets: str | None = Field(default=None, max_length=20)
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover: bool | None = None
    dinghies_color: str | None = Field(default=None, max_length=40)
    color_and_markings: str = Field(min_length=1, max_length=255)


class AircraftUpdate(BaseModel):
    alias: str | None = Field(default=None, max_length=120)
    identification: str | None = Field(default=None, min_length=1, max_length=20)
    icao_type_designator: str | None = Field(default=None, min_length=1, max_length=10)
    wake_turbulence_category: WakeTurbulenceCat | None = None
    equipment_com_nav: str | None = Field(default=None, min_length=1, max_length=80)
    equipment_surveillance: str | None = Field(default=None, min_length=1, max_length=80)
    pbn_capabilities: str | None = Field(default=None, max_length=80)
    emergency_radio: str | None = Field(default=None, max_length=20)
    survival_equipment: str | None = Field(default=None, max_length=20)
    life_jackets: str | None = Field(default=None, max_length=20)
    dinghies_number: int | None = Field(default=None, ge=0)
    dinghies_capacity: int | None = Field(default=None, ge=0)
    dinghies_cover: bool | None = None
    dinghies_color: str | None = Field(default=None, max_length=40)
    color_and_markings: str | None = Field(default=None, min_length=1, max_length=255)


class AircraftPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    alias: str | None
    is_active: bool
    identification: str
    icao_type_designator: str
    wake_turbulence_category: str
    equipment_com_nav: str
    equipment_surveillance: str
    pbn_capabilities: str | None
    emergency_radio: str | None
    survival_equipment: str | None
    life_jackets: str | None
    dinghies_number: int | None
    dinghies_capacity: int | None
    dinghies_cover: bool | None
    dinghies_color: str | None
    color_and_markings: str
    created_at: datetime
    updated_at: datetime


class AircraftDeleteResponse(BaseModel):
    deleted: bool
```

- [ ] **Step 4: Add aircraft service**

Create `app/services/aircraft_service.py`:

```python
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft
from app.models.user import Role, User
from app.repositories.aircraft_repository import AircraftRepository
from app.schemas.aircraft import AircraftCreate, AircraftUpdate


class AircraftService:
    @staticmethod
    def _ensure_pilot(current_user: User) -> None:
        if current_user.role != Role.PILOT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only pilots can manage aircraft")

    @staticmethod
    async def create_for_pilot(
        db: AsyncSession,
        *,
        current_user: User,
        payload: AircraftCreate,
    ) -> Aircraft:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftRepository.create(
            db,
            owner_user_id=current_user.id,
            **payload.model_dump(),
        )
        await db.commit()
        await db.refresh(aircraft)
        return aircraft

    @staticmethod
    async def list_for_pilot(db: AsyncSession, *, current_user: User) -> list[Aircraft]:
        AircraftService._ensure_pilot(current_user)
        return await AircraftRepository.list_active_by_owner(db, owner_user_id=current_user.id)

    @staticmethod
    async def get_for_pilot(
        db: AsyncSession,
        *,
        current_user: User,
        aircraft_id: UUID,
    ) -> Aircraft | None:
        AircraftService._ensure_pilot(current_user)
        return await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )

    @staticmethod
    async def update_for_pilot(
        db: AsyncSession,
        *,
        current_user: User,
        aircraft_id: UUID,
        payload: AircraftUpdate,
    ) -> Aircraft:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftService.get_for_pilot(db, current_user=current_user, aircraft_id=aircraft_id)
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
        fields = payload.model_dump(exclude_unset=True)
        await AircraftRepository.update(aircraft, **fields)
        await db.commit()
        await db.refresh(aircraft)
        return aircraft

    @staticmethod
    async def delete_for_pilot(
        db: AsyncSession,
        *,
        current_user: User,
        aircraft_id: UUID,
    ) -> bool:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftService.get_for_pilot(db, current_user=current_user, aircraft_id=aircraft_id)
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
        await AircraftRepository.soft_delete(aircraft)
        await db.commit()
        return True
```

- [ ] **Step 5: Run service tests to verify they pass**

Run: `pytest app/tests/test_aircraft_service.py -v`

Expected: PASS for both service tests.

- [ ] **Step 6: Commit checkpoint if authorized**

If the user explicitly authorized commits, run:

```bash
git add app/schemas/aircraft.py app/services/aircraft_service.py app/tests/test_aircraft_service.py
git commit -m "feat: add pilot aircraft service"
```

---

### Task 3: Pilot Aircraft API Routes

**Files:**

- Create: `app/routes/aircraft.py`
- Modify: `app/main.py`
- Test: `app/tests/test_aircraft.py`

- [ ] **Step 1: Write failing endpoint tests**

Create `app/tests/test_aircraft.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models import aircraft as _aircraft_model


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


async def register_pilot(client: AsyncClient, email="pilot@example.com") -> str:
    response = await client.post(
        "/auth/register/pilot",
        json={
            "email": email,
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    return response.json()["access_token"]


def aircraft_payload(identification="lv-abc") -> dict:
    return {
        "alias": "Club Cessna",
        "identification": identification,
        "icao_type_designator": "c172",
        "wake_turbulence_category": "L",
        "equipment_com_nav": "SDFG",
        "equipment_surveillance": "C",
        "pbn_capabilities": None,
        "emergency_radio": None,
        "survival_equipment": None,
        "life_jackets": None,
        "dinghies_number": None,
        "dinghies_capacity": None,
        "dinghies_cover": None,
        "dinghies_color": None,
        "color_and_markings": "White and blue",
    }


@pytest.mark.asyncio
async def test_pilot_can_create_list_get_patch_and_soft_delete_aircraft(client):
    access_token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post("/pilot/aircraft", json=aircraft_payload(), headers=headers)
    aircraft_id = create_response.json()["id"]
    list_response = await client.get("/pilot/aircraft", headers=headers)
    get_response = await client.get(f"/pilot/aircraft/{aircraft_id}", headers=headers)
    patch_response = await client.patch(
        f"/pilot/aircraft/{aircraft_id}",
        json={"alias": "Updated alias", "color_and_markings": "White"},
        headers=headers,
    )
    delete_response = await client.delete(f"/pilot/aircraft/{aircraft_id}", headers=headers)
    list_after_delete = await client.get("/pilot/aircraft", headers=headers)
    get_after_delete = await client.get(f"/pilot/aircraft/{aircraft_id}", headers=headers)

    assert create_response.status_code == 201
    assert create_response.json()["identification"] == "LV-ABC"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert get_response.status_code == 200
    assert get_response.json()["id"] == aircraft_id
    assert patch_response.status_code == 200
    assert patch_response.json()["alias"] == "Updated alias"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert list_after_delete.json() == []
    assert get_after_delete.status_code == 404


@pytest.mark.asyncio
async def test_aircraft_routes_require_authentication(client):
    response = await client.get("/pilot/aircraft")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pilot_cannot_get_aircraft_owned_by_another_pilot(client):
    owner_token = await register_pilot(client, email="owner@example.com")
    other_token = await register_pilot(client, email="other@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    create_response = await client.post("/pilot/aircraft", json=aircraft_payload("lv-own"), headers=owner_headers)
    aircraft_id = create_response.json()["id"]
    other_get_response = await client.get(f"/pilot/aircraft/{aircraft_id}", headers=other_headers)

    assert create_response.status_code == 201
    assert other_get_response.status_code == 404
```

- [ ] **Step 2: Run endpoint tests to verify they fail**

Run: `pytest app/tests/test_aircraft.py -v`

Expected: FAIL with `404 Not Found` for `/pilot/aircraft` or `ModuleNotFoundError` for route wiring.

- [ ] **Step 3: Add aircraft routes**

Create `app/routes/aircraft.py`:

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.schemas.aircraft import AircraftCreate, AircraftDeleteResponse, AircraftPublic, AircraftUpdate
from app.services.aircraft_service import AircraftService

router = APIRouter(prefix="/pilot/aircraft", tags=["pilot-aircraft"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_aircraft(
    payload: AircraftCreate,
    current_user: CurrentActiveUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AircraftPublic:
    aircraft = await AircraftService.create_for_pilot(db, current_user=current_user, payload=payload)
    return AircraftPublic.model_validate(aircraft)


@router.get("")
async def list_aircraft(
    current_user: CurrentActiveUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AircraftPublic]:
    aircraft = await AircraftService.list_for_pilot(db, current_user=current_user)
    return [AircraftPublic.model_validate(item) for item in aircraft]


@router.get("/{aircraft_id}")
async def get_aircraft(
    aircraft_id: UUID,
    current_user: CurrentActiveUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AircraftPublic:
    aircraft = await AircraftService.get_for_pilot(db, current_user=current_user, aircraft_id=aircraft_id)
    if aircraft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
    return AircraftPublic.model_validate(aircraft)


@router.patch("/{aircraft_id}")
async def update_aircraft(
    aircraft_id: UUID,
    payload: AircraftUpdate,
    current_user: CurrentActiveUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AircraftPublic:
    aircraft = await AircraftService.update_for_pilot(
        db,
        current_user=current_user,
        aircraft_id=aircraft_id,
        payload=payload,
    )
    return AircraftPublic.model_validate(aircraft)


@router.delete("/{aircraft_id}")
async def delete_aircraft(
    aircraft_id: UUID,
    current_user: CurrentActiveUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AircraftDeleteResponse:
    deleted = await AircraftService.delete_for_pilot(db, current_user=current_user, aircraft_id=aircraft_id)
    return AircraftDeleteResponse(deleted=deleted)
```

- [ ] **Step 4: Include the aircraft router**

Modify `app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import aircraft, auth, health
from app.core import database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if database.engine is not None:
        await database.engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Jetpass Backend Core",
        lifespan=lifespan,
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(aircraft.router)
    return application


app = create_app()
```

- [ ] **Step 5: Run endpoint tests to verify they pass**

Run: `pytest app/tests/test_aircraft.py -v`

Expected: PASS for all aircraft endpoint tests.

- [ ] **Step 6: Commit checkpoint if authorized**

If the user explicitly authorized commits, run:

```bash
git add app/routes/aircraft.py app/main.py app/tests/test_aircraft.py
git commit -m "feat: add pilot aircraft routes"
```

---

### Task 4: Full Verification And Cleanup

**Files:**

- Modify only files required to fix failures found by verification.
- Test: full suite under `app/tests`.

- [ ] **Step 1: Run all tests**

Run: `pytest -v`

Expected: PASS for existing auth, security, health, repository, service, and aircraft tests.

- [ ] **Step 2: Fix any verification failure with TDD discipline**

If a behavior is missing, write or adjust the failing test first, run it to observe the expected failure, then implement the minimal production change. For example, if route serialization fails for `wake_turbulence_category`, keep this assertion in `app/tests/test_aircraft.py`:

```python
assert create_response.json()["wake_turbulence_category"] == "L"
```

Then update only the schema/model serialization needed to make that assertion pass.

- [ ] **Step 3: Run focused tests after any fix**

Run the focused failing test first, such as:

```bash
pytest app/tests/test_aircraft.py::test_pilot_can_create_list_get_patch_and_soft_delete_aircraft -v
```

Expected: PASS for the focused test.

- [ ] **Step 4: Run all tests again**

Run: `pytest -v`

Expected: PASS for the full suite with no unexpected warnings or errors.

- [ ] **Step 5: Inspect git diff**

Run: `git diff -- app/models/aircraft.py app/models/user.py app/repositories/aircraft_repository.py app/schemas/aircraft.py app/services/aircraft_service.py app/routes/aircraft.py app/main.py app/tests/test_aircraft_repositories.py app/tests/test_aircraft_service.py app/tests/test_aircraft.py`

Expected: Diff only contains aircraft-management changes and no unrelated edits.

- [ ] **Step 6: Final commit if authorized**

If the user explicitly authorized commits and previous checkpoints were not committed, run:

```bash
git add app/models/aircraft.py app/models/user.py app/repositories/aircraft_repository.py app/schemas/aircraft.py app/services/aircraft_service.py app/routes/aircraft.py app/main.py app/tests/test_aircraft_repositories.py app/tests/test_aircraft_service.py app/tests/test_aircraft.py docs/superpowers/specs/2026-05-08-pilot-aircraft-management-design.md docs/superpowers/plans/2026-05-08-pilot-aircraft-management.md
git commit -m "feat: add pilot aircraft management"
```

---

## Self-Review

- Spec coverage: model, schemas, repository, service, routes, soft delete, pilot ownership, error behavior, and tests are covered by Tasks 1 through 4.
- Placeholder scan: no placeholders remain; every task includes concrete file paths, commands, expected results, and code snippets.
- Type consistency: route, service, repository, schema, and test names consistently use `AircraftCreate`, `AircraftUpdate`, `AircraftPublic`, `AircraftDeleteResponse`, `AircraftService`, and `AircraftRepository`.

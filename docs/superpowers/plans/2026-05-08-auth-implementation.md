# Jetpass Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build pilot-focused authentication with JSON registration/login, JWT access tokens, opaque persisted refresh tokens, refresh rotation, logout, and current-user lookup.

**Architecture:** Keep the existing MVC layout. Controllers expose FastAPI routes, services own auth business rules, repositories own SQLAlchemy queries, models define persistence, schemas define API contracts, and `core/security.py` centralizes password and token primitives.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, PyJWT, pwdlib, pytest, httpx, aiosqlite for test database setup.

---

## Scope And File Map

Create:

- `app/core/security.py`: password hashing, JWT creation/validation, refresh token generation and hashing, current-user dependencies.
- `app/models/user.py`: `User` SQLAlchemy model and `Role` enum.
- `app/models/auth_session.py`: persisted refresh-token session model.
- `app/repositories/user_repository.py`: user lookup and create queries.
- `app/repositories/auth_session_repository.py`: refresh-session lookup, create, revoke queries.
- `app/schemas/auth.py`: request and response schemas.
- `app/services/auth_service.py`: register, login, refresh, logout orchestration.
- `app/routes/auth.py`: `/auth` routes.
- `app/tests/test_auth.py`: integration tests with an async SQLite test database.

Modify:

- `pyproject.toml`: add JWT, hashing, email validation, and test DB dependencies.
- `app/core/config.py`: add token algorithm and expiration settings.
- `app/main.py`: include auth router.
- `app/models/__init__.py`: import models so metadata sees tables.

Do not create `PilotProfile` in this auth implementation. The approved design defers pilot profile data until a profile-completion endpoint exists.

Commit checkpoints are included for execution discipline, but in this repository do not run `git commit` unless the user explicitly authorizes commits during execution.

---

### Task 1: Dependencies, Settings, And Security Primitives

**Files:**

- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Create: `app/core/security.py`
- Test: `app/tests/test_security.py`

- [ ] **Step 1: Write failing tests for password hashing, JWT validation, and refresh hashing**

Create `app/tests/test_security.py`:

```python
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_verification():
    password_hash = get_password_hash("safe-password")

    assert password_hash != "safe-password"
    assert verify_password("safe-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_access_token_contains_expected_claims():
    token = create_access_token(
        subject="user-123",
        role="pilot",
        expires_delta=timedelta(minutes=5),
    )

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["role"] == "pilot"
    assert payload["type"] == "access"


def test_decode_rejects_non_access_token():
    token = create_access_token(
        subject="user-123",
        role="pilot",
        expires_delta=timedelta(minutes=5),
        token_type="refresh",
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)

    assert exc_info.value.status_code == 401


def test_refresh_token_is_opaque_and_hashable():
    token = generate_refresh_token()
    token_hash = hash_refresh_token(token)

    assert len(token) >= 43
    assert token_hash != token
    assert hash_refresh_token(token) == token_hash
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_security.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.security'`.

- [ ] **Step 3: Add dependencies**

Update `pyproject.toml` dependencies:

```toml
dependencies = [
    "asyncpg>=0.31.0",
    "email-validator>=2.3.0",
    "fastapi>=0.136.0",
    "httpx>=0.28.1",
    "pwdlib[argon2]>=0.3.0",
    "pydantic-settings>=2.13.1",
    "pyjwt>=2.10.1",
    "python-dotenv>=1.2.2",
    "redis>=7.4.0",
    "sqlalchemy>=2.0.49",
    "uvicorn[standard]>=0.44.0",
]

[dependency-groups]
dev = [
    "aiosqlite>=0.21.0",
    "httpx>=0.28.1",
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
]
```

Run: `uv sync`

Expected: dependencies install successfully and `uv.lock` updates.

- [ ] **Step 4: Add auth settings**

Modify `app/core/config.py` so `Settings` includes:

```python
class Settings(BaseSettings):
    APP_ENV: str = "dev"

    DEV_DATABASE_URL: str | None = None
    DEV_REDIS_URL: str | None = None

    TEST_DATABASE_URL: str | None = None
    TEST_REDIS_URL: str | None = None

    PROD_DATABASE_URL: str | None = None
    PROD_REDIS_URL: str | None = None

    SECRET_KEY: str = Field(default="dev-only-change-me")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"
```

Keep the existing `model_config`, `DATABASE_URL`, and `REDIS_URL` properties unchanged.

- [ ] **Step 5: Implement security primitives**

Create `app/core/security.py`:

```python
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
    token_type: str = "access",
) -> str:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    if payload.get("type") != "access" or payload.get("sub") is None:
        raise credentials_exception

    return payload


def generate_refresh_token() -> str:
    return token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.repositories.user_repository import UserRepository

    payload = decode_access_token(token)
    user_id = UUID(payload["sub"])
    user = await UserRepository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(current_user: Annotated[object, Depends(get_current_user)]):
    if not getattr(current_user, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user
```

- [ ] **Step 6: Run security tests**

Run: `pytest app/tests/test_security.py -v`

Expected: PASS for all tests in `test_security.py`.

- [ ] **Step 7: Commit checkpoint if commits are authorized**

Run only if the user requested commits:

```bash
git add pyproject.toml uv.lock app/core/config.py app/core/security.py app/tests/test_security.py
git commit -m "feat: add auth security primitives"
```

---

### Task 2: Persistence Models And Repositories

**Files:**

- Create: `app/models/user.py`
- Create: `app/models/auth_session.py`
- Modify: `app/models/__init__.py`
- Create: `app/repositories/user_repository.py`
- Create: `app/repositories/auth_session_repository.py`
- Test: `app/tests/test_auth_repositories.py`

- [ ] **Step 1: Write failing repository tests**

Create `app/tests/test_auth_repositories.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models.user import Role
from app.repositories.auth_session_repository import AuthSessionRepository
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


@pytest.mark.asyncio
async def test_user_repository_creates_and_fetches_by_email(db_session):
    user = await UserRepository.create(
        db_session,
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
    )
    await db_session.commit()

    fetched = await UserRepository.get_by_email(db_session, "pilot@example.com")

    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.role == Role.PILOT
    assert fetched.is_active is True
    assert fetched.is_verified is False


@pytest.mark.asyncio
async def test_auth_session_repository_rotates_refresh_token(db_session):
    user = await UserRepository.create(
        db_session,
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone="+541111111111",
        role=Role.PILOT,
    )
    session = await AuthSessionRepository.create(
        db_session,
        user_id=user.id,
        refresh_token_hash="old-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        user_agent="pytest",
        ip_address="127.0.0.1",
        device_name="test-device",
    )
    await db_session.commit()

    active = await AuthSessionRepository.get_active_by_refresh_token_hash(
        db_session,
        "old-hash",
        now=datetime.now(timezone.utc),
    )
    assert active is not None
    assert active.id == session.id

    await AuthSessionRepository.revoke(db_session, session, now=datetime.now(timezone.utc))
    await db_session.commit()

    reused = await AuthSessionRepository.get_active_by_refresh_token_hash(
        db_session,
        "old-hash",
        now=datetime.now(timezone.utc),
    )
    assert reused is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_auth_repositories.py -v`

Expected: FAIL with missing `app.models.user` or missing repository modules.

- [ ] **Step 3: Implement user model**

Create `app/models/user.py`:

```python
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(StrEnum):
    PILOT = "pilot"
    ATC_AUTHORITY = "atc_authority"
    AIRPORT_OPERATOR = "airport_operator"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    auth_sessions = relationship(
        "AuthSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
```

- [ ] **Step 4: Implement auth session model**

Create `app/models/auth_session.py`:

```python
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
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

    user = relationship("User", back_populates="auth_sessions")
```

- [ ] **Step 5: Import models for metadata registration**

Modify `app/models/__init__.py`:

```python
from app.models import auth_session, user

__all__ = ["auth_session", "user"]
```

- [ ] **Step 6: Implement user repository**

Create `app/repositories/user_repository.py`:

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Role, User


class UserRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: UUID) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        phone: str | None,
        role: Role,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        await db.flush()
        return user
```

- [ ] **Step 7: Implement auth session repository**

Create `app/repositories/auth_session_repository.py`:

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession


class AuthSessionRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        db.add(auth_session)
        await db.flush()
        return auth_session

    @staticmethod
    async def get_active_by_refresh_token_hash(
        db: AsyncSession,
        refresh_token_hash: str,
        *,
        now: datetime,
    ) -> AuthSession | None:
        result = await db.execute(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == refresh_token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke(db: AsyncSession, auth_session: AuthSession, *, now: datetime) -> None:
        auth_session.revoked_at = now
        await db.flush()
```

- [ ] **Step 8: Run repository tests**

Run: `pytest app/tests/test_auth_repositories.py -v`

Expected: PASS for all repository tests.

- [ ] **Step 9: Commit checkpoint if commits are authorized**

Run only if the user requested commits:

```bash
git add app/models app/repositories app/tests/test_auth_repositories.py
git commit -m "feat: add auth persistence models"
```

---

### Task 3: Registration And Login API

**Files:**

- Create: `app/schemas/auth.py`
- Create: `app/services/auth_service.py`
- Create: `app/routes/auth.py`
- Modify: `app/main.py`
- Test: `app/tests/test_auth.py`

- [ ] **Step 1: Write failing integration tests for registration and login**

Create `app/tests/test_auth.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import auth_session as _auth_session_model
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


@pytest.mark.asyncio
async def test_register_pilot_returns_tokens_and_public_user(client):
    response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "Pilot@Example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": "+541111111111",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "pilot@example.com"
    assert body["user"]["role"] == "pilot"
    assert body["user"]["is_active"] is True
    assert body["user"]["is_verified"] is False
    assert "password_hash" not in body["user"]


@pytest.mark.asyncio
async def test_register_pilot_rejects_duplicate_email(client):
    payload = {
        "email": "pilot@example.com",
        "password": "safe-password-123",
        "first_name": "Amelia",
        "last_name": "Earhart",
        "phone": None,
    }
    first = await client.post("/auth/register/pilot", json=payload)
    second = await client.post("/auth/register/pilot", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_tokens(client):
    await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )

    response = await client.post(
        "/auth/login",
        json={"email": "pilot@example.com", "password": "safe-password-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "pilot@example.com"


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(client):
    await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )

    response = await client.post(
        "/auth/login",
        json={"email": "pilot@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_auth.py -v`

Expected: FAIL with `404 Not Found` for `/auth/register/pilot` or missing auth modules.

- [ ] **Step 3: Implement auth schemas**

Create `app/schemas/auth.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PilotRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    device_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone: str | None
    role: str
    is_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class LogoutResponse(BaseModel):
    revoked: bool
```

- [ ] **Step 4: Implement auth service**

Create `app/services/auth_service.py`:

```python
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from app.models.user import Role, User
from app.repositories.auth_session_repository import AuthSessionRepository
from app.repositories.user_repository import UserRepository


class AuthService:
    @staticmethod
    async def register_pilot(
        db: AsyncSession,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        phone: str | None,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        existing_user = await UserRepository.get_by_email(db, email)
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = await UserRepository.create(
            db,
            email=email,
            password_hash=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=Role.PILOT,
        )
        access_token, refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        await db.refresh(user)
        return user, access_token, refresh_token, expires_in

    @staticmethod
    async def login(
        db: AsyncSession,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        user = await UserRepository.get_by_email(db, email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

        access_token, refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        return user, access_token, refresh_token, expires_in

    @staticmethod
    async def _create_token_pair(
        db: AsyncSession,
        *,
        user: User,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[str, str, int]:
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        access_token = create_access_token(subject=str(user.id), role=user.role.value)
        refresh_token = generate_refresh_token()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await AuthSessionRepository.create(
            db,
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        return access_token, refresh_token, expires_in
```

- [ ] **Step 5: Implement auth controller**

Create `app/routes/auth.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import AuthTokenResponse, LoginRequest, PilotRegisterRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register/pilot", status_code=status.HTTP_201_CREATED)
async def register_pilot(
    payload: PilotRegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.register_pilot(
        db,
        email=str(payload.email),
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=payload.device_name,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.login(
        db,
        email=str(payload.email),
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=payload.device_name,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )
```

- [ ] **Step 6: Include auth router**

Modify `app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controllers import auth, health
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
    return application


app = create_app()
```

- [ ] **Step 7: Run registration and login tests**

Run: `pytest app/tests/test_auth.py -v`

Expected: PASS for registration duplicate/login tests currently in the file.

- [ ] **Step 8: Run existing health test**

Run: `pytest app/tests/test_health.py -v`

Expected: PASS.

- [ ] **Step 9: Commit checkpoint if commits are authorized**

Run only if the user requested commits:

```bash
git add app/schemas/auth.py app/services/auth_service.py app/routes/auth.py app/main.py app/tests/test_auth.py
git commit -m "feat: add pilot registration and login"
```

---

### Task 4: Refresh, Logout, And Current User

**Files:**

- Modify: `app/services/auth_service.py`
- Modify: `app/routes/auth.py`
- Modify: `app/core/security.py`
- Modify: `app/tests/test_auth.py`

- [ ] **Step 1: Add failing tests for `/auth/me`, refresh rotation, and logout**

Append to `app/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_me_returns_current_user_with_valid_access_token(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    access_token = register_response.json()["access_token"]

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "pilot@example.com"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client):
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_rejects_reuse(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    old_refresh_token = register_response.json()["refresh_token"]

    refresh_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert refresh_response.status_code == 200
    new_body = refresh_response.json()
    assert new_body["access_token"]
    assert new_body["refresh_token"] != old_refresh_token

    reuse_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reuse_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    refresh_token = register_response.json()["refresh_token"]

    logout_response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    refresh_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 200
    assert logout_response.json() == {"revoked": True}
    assert refresh_response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest app/tests/test_auth.py -v`

Expected: FAIL with `404 Not Found` for `/auth/me`, `/auth/refresh`, or `/auth/logout`.

- [ ] **Step 3: Tighten current-user dependency typing**

Modify the bottom of `app/core/security.py`:

```python
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.repositories.user_repository import UserRepository

    payload = decode_access_token(token)
    user_id = UUID(payload["sub"])
    user = await UserRepository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[object, Depends(get_current_user)]


async def get_current_active_user(current_user: CurrentUserDep):
    if not getattr(current_user, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


CurrentActiveUserDep = Annotated[object, Depends(get_current_active_user)]
```

- [ ] **Step 4: Add refresh and logout service methods**

Append methods inside `AuthService` in `app/services/auth_service.py`:

```python
    @staticmethod
    async def refresh(
        db: AsyncSession,
        *,
        refresh_token: str,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        now = datetime.now(timezone.utc)
        auth_session = await AuthSessionRepository.get_active_by_refresh_token_hash(
            db,
            hash_refresh_token(refresh_token),
            now=now,
        )
        if auth_session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user = await UserRepository.get_by_id(db, auth_session.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

        await AuthSessionRepository.revoke(db, auth_session, now=now)
        access_token, new_refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        return user, access_token, new_refresh_token, expires_in

    @staticmethod
    async def logout(db: AsyncSession, *, refresh_token: str) -> bool:
        now = datetime.now(timezone.utc)
        auth_session = await AuthSessionRepository.get_active_by_refresh_token_hash(
            db,
            hash_refresh_token(refresh_token),
            now=now,
        )
        if auth_session is None:
            return True

        await AuthSessionRepository.revoke(db, auth_session, now=now)
        await db.commit()
        return True
```

- [ ] **Step 5: Add refresh, logout, and me routes**

Append to `app/routes/auth.py`:

```python
from app.core.security import CurrentActiveUserDep
from app.schemas.auth import LogoutRequest, LogoutResponse, RefreshRequest, UserPublic


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.refresh(
        db,
        refresh_token=payload.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=None,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogoutResponse:
    revoked = await AuthService.logout(db, refresh_token=payload.refresh_token)
    return LogoutResponse(revoked=revoked)


@router.get("/me")
async def me(current_user: CurrentActiveUserDep) -> UserPublic:
    return UserPublic.model_validate(current_user)
```

If duplicate imports appear, merge them into one import block at the top of `app/routes/auth.py`:

```python
from app.core.security import CurrentActiveUserDep
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    PilotRegisterRequest,
    RefreshRequest,
    UserPublic,
)
```

- [ ] **Step 6: Run auth integration tests**

Run: `pytest app/tests/test_auth.py -v`

Expected: PASS for registration, duplicate email, login, current user, refresh rotation, and logout tests.

- [ ] **Step 7: Run full test suite**

Run: `pytest -v`

Expected: PASS for all tests.

- [ ] **Step 8: Commit checkpoint if commits are authorized**

Run only if the user requested commits:

```bash
git add app/core/security.py app/services/auth_service.py app/routes/auth.py app/tests/test_auth.py
git commit -m "feat: add refresh logout and current user auth"
```

---

### Task 5: Final Verification And API Contract Review

**Files:**

- Modify only if verification exposes a concrete issue.
- Review: `docs/superpowers/specs/2026-05-08-auth-design.md`
- Review: `docs/superpowers/plans/2026-05-08-auth-implementation.md`

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`

Expected: all tests pass.

- [ ] **Step 2: Verify OpenAPI app imports**

Run: `python -c "from app.main import app; print(app.title)"`

Expected output contains `Jetpass Backend Core`.

- [ ] **Step 3: Verify auth routes are registered**

Run: `python -c "from app.main import app; print(sorted(route.path for route in app.routes if route.path.startswith('/auth')))"`

Expected output includes:

```text
'/auth/login'
'/auth/logout'
'/auth/me'
'/auth/refresh'
'/auth/register/pilot'
```

- [ ] **Step 4: Review spec coverage**

Confirm implementation covers:

- Pilot registration with `role=pilot`, `is_active=true`, `is_verified=false`.
- JSON login.
- JWT access token with `sub`, `role`, `type=access`, `exp`.
- Opaque persisted refresh token stored as hash.
- Refresh token rotation and reuse rejection.
- Logout revocation.
- `/auth/me` protected by bearer token.
- MVC file structure.

- [ ] **Step 5: Commit checkpoint if commits are authorized**

Run only if the user requested commits:

```bash
git status --short
git add app pyproject.toml uv.lock docs/superpowers/specs/2026-05-08-auth-design.md docs/superpowers/plans/2026-05-08-auth-implementation.md
git commit -m "feat: implement pilot authentication"
```

---

## Self-Review Notes

- Spec coverage: every approved requirement has a task: registration/login in Task 3, refresh/logout/me in Task 4, security primitives in Task 1, persistence in Task 2, verification in Task 5.
- Placeholder scan: no unresolved markers or unspecified implementation steps remain.
- Type consistency: `Role.PILOT` stores value `pilot`; token claims use `user.role.value`; API responses serialize role as a string; refresh tokens are opaque strings and only hashes are stored.
- Scope check: this is one subsystem, auth for pilot-focused mobile use. Pilot profile completion, password reset, verification enforcement, and session listing remain outside this plan by design.

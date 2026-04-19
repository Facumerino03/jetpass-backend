from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass

engine = None
AsyncSessionLocal = None

_db_url = settings.DATABASE_URL
if _db_url:
    engine = create_async_engine(_db_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError("Database is not configured (DATABASE_URL is unset).")
    async with AsyncSessionLocal() as session:
        yield session

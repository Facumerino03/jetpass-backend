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

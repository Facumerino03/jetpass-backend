from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controllers import health
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
    return application


app = create_app()

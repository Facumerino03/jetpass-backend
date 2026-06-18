from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import aircraft, auth, flight_plans, health
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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(aircraft.router)
    application.include_router(flight_plans.router)
    return application


app = create_app()

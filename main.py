"""Entrypoint for `uvicorn main:app` from project root."""

from app.main import app

__all__ = ["app"]

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
            "weather": None,
            "aerodrome_geo": None,
            "aerodrome_catalog_sync": None,
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

    @staticmethod
    def unavailable_aircraft_type_response(*, designator: str) -> dict[str, Any]:
        normalized = designator.strip().upper()
        return {
            "designator": normalized,
            "is_valid": None,
            "entry": None,
            "source": None,
            "alerts": [
                {
                    "level": "warning",
                    "code": "INTELLIGENCE_UNAVAILABLE",
                    "message": "Aeronautical intelligence is unavailable",
                }
            ],
            "messages": [],
            "metadata": {},
            "unavailable": True,
        }

    async def verify_aircraft_type(self, designator: str) -> dict[str, Any]:
        normalized = designator.strip().upper()
        if not self.base_url:
            return self.unavailable_aircraft_type_response(designator=normalized)

        path = f"/intelligence/aircraft-types/{normalized}"
        if self.http_client is not None:
            try:
                response = await self.http_client.get(path)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                return self.unavailable_aircraft_type_response(designator=normalized)

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.get(path)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError:
            return self.unavailable_aircraft_type_response(designator=normalized)

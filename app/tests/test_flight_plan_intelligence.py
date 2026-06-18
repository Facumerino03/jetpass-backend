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

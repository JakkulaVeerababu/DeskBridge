"""
Unit tests for FreshdeskClient retry / backoff logic.

Uses respx to mock the HTTP transport and monkeypatches asyncio.sleep
so tests run instantly without real waits.
"""
import base64

import httpx
import pytest
import respx

import deskbridge.client as client_mod
from deskbridge.client import FreshdeskClient, FreshdeskError
from deskbridge.config import Settings

# Shared minimal settings for tests
S = Settings(domain="testco", api_key="testkey", max_retries=3)
BASE = "https://testco.freshdesk.com/api/v2"
TICKETS_URL = f"{BASE}/tickets"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch) -> list[float]:
    """Replace asyncio.sleep with a no-op collector so tests run instantly."""
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fake_sleep)
    return slept


# ---------------------------------------------------------------------------
# 429 handling
# ---------------------------------------------------------------------------

@respx.mock
async def test_429_honours_retry_after_header(no_sleep):
    """Client must use the Retry-After value, not its own backoff."""
    respx.get(TICKETS_URL).mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json=[{"id": 1}]),
    ])
    result = await FreshdeskClient(S).get("/tickets")
    assert result == [{"id": 1}]
    assert no_sleep == [7.0], f"expected [7.0], got {no_sleep}"


@respx.mock
async def test_429_retries_exhausted_raises(no_sleep):
    """After max_retries+1 attempts all returning 429, raise FreshdeskError(429)."""
    respx.get(TICKETS_URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )
    with pytest.raises(FreshdeskError) as exc:
        await FreshdeskClient(S).get("/tickets")
    assert exc.value.status == 429
    # should have slept max_retries times before giving up
    assert len(no_sleep) == S.max_retries


@respx.mock
async def test_429_caps_retry_after_at_60(no_sleep):
    """Retry-After larger than 60 s must be capped to 60 s."""
    respx.get(TICKETS_URL).mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "999"}),
        httpx.Response(200, json=[]),
    ])
    await FreshdeskClient(S).get("/tickets")
    assert no_sleep[0] == 60.0


@respx.mock
async def test_429_invalid_retry_after_falls_back_to_backoff(no_sleep):
    """Non-numeric Retry-After should fall back to exponential backoff."""
    respx.get(TICKETS_URL).mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "soon"}),
        httpx.Response(200, json=[]),
    ])
    await FreshdeskClient(S).get("/tickets")
    assert len(no_sleep) == 1
    # attempt=0 → backoff in [1.0, 1.5)
    assert 1.0 <= no_sleep[0] < 1.6


# ---------------------------------------------------------------------------
# 5xx handling
# ---------------------------------------------------------------------------

@respx.mock
async def test_5xx_retries_with_exponential_backoff(no_sleep):
    """503 should retry with backoff; third attempt succeeds."""
    respx.get(TICKETS_URL).mock(side_effect=[
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json=[{"id": 42}]),
    ])
    result = await FreshdeskClient(S).get("/tickets")
    assert result == [{"id": 42}]
    assert len(no_sleep) == 2
    # attempt 0 → [1.0, 1.5), attempt 1 → [2.0, 2.5)
    assert 1.0 <= no_sleep[0] < 1.6
    assert 2.0 <= no_sleep[1] < 2.6


@respx.mock
async def test_5xx_exhausted_raises(no_sleep):
    respx.get(TICKETS_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(FreshdeskError) as exc:
        await FreshdeskClient(S).get("/tickets")
    assert exc.value.status == 500
    assert len(no_sleep) == S.max_retries


# ---------------------------------------------------------------------------
# Non-retried client errors
# ---------------------------------------------------------------------------

@respx.mock
async def test_401_not_retried(no_sleep):
    respx.get(TICKETS_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(FreshdeskError) as exc:
        await FreshdeskClient(S).get("/tickets")
    assert exc.value.status == 401
    assert no_sleep == [], "401 must never be retried"


@respx.mock
async def test_403_not_retried(no_sleep):
    respx.get(TICKETS_URL).mock(return_value=httpx.Response(403))
    with pytest.raises(FreshdeskError) as exc:
        await FreshdeskClient(S).get("/tickets")
    assert exc.value.status == 403
    assert no_sleep == []


@respx.mock
async def test_404_not_retried(no_sleep):
    respx.get(TICKETS_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(FreshdeskError) as exc:
        await FreshdeskClient(S).get("/tickets")
    assert exc.value.status == 404
    assert no_sleep == []


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@respx.mock
async def test_basic_auth_uses_api_key_as_username_and_X_as_password():
    """Freshdesk requires Basic auth with key:X encoded in Base64."""
    route = respx.get(TICKETS_URL).mock(return_value=httpx.Response(200, json=[]))
    await FreshdeskClient(S).get("/tickets")
    auth_header = route.calls[0].request.headers["authorization"]
    expected = "Basic " + base64.b64encode(b"testkey:X").decode()
    assert auth_header == expected


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@respx.mock
async def test_returns_parsed_json_on_200():
    payload = [{"id": 1, "subject": "Test"}]
    respx.get(TICKETS_URL).mock(return_value=httpx.Response(200, json=payload))
    result = await FreshdeskClient(S).get("/tickets")
    assert result == payload


@respx.mock
async def test_passes_query_params():
    route = respx.get(TICKETS_URL).mock(return_value=httpx.Response(200, json=[]))
    await FreshdeskClient(S).get("/tickets", {"page": 2, "per_page": 10})
    assert route.calls[0].request.url.params["page"] == "2"
    assert route.calls[0].request.url.params["per_page"] == "10"

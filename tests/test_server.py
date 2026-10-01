"""
Tests for the MCP server tool layer (list_tickets, get_ticket, search_tickets).

Uses respx to mock Freshdesk HTTP responses and injects a real FreshdeskClient
with a mock transport via monkeypatching the server's _deps() function.
"""
import httpx
import pytest
import respx

from deskbridge.config import Settings
from deskbridge.client import FreshdeskClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

S = Settings(domain="testco", api_key="testkey", mask_pii=True, max_retries=1)
BASE = "https://testco.freshdesk.com/api/v2"

FAKE_TICKET = {
    "id": 101,
    "subject": "Refund for ravi.kumar@gmail.com",
    "status": 2,
    "priority": 3,
    "created_at": "2026-09-01T10:00:00Z",
    "updated_at": "2026-09-02T12:00:00Z",
    "due_by": "2026-09-05T10:00:00Z",
    "tags": ["refund"],
    "requester_id": 999,
    "description_text": "Please refund order. Call 9876543210.",
    "conversations": [
        {
            "id": 201,
            "incoming": True,
            "private": False,
            "created_at": "2026-09-01T11:00:00Z",
            "body_text": "We received your request from test@example.com",
        }
    ],
}


@pytest.fixture
def patched_deps(monkeypatch):
    """Inject a real client backed by the respx mock transport."""
    client = FreshdeskClient(S)

    def _fake_deps():
        return S, client

    import deskbridge.server as srv
    monkeypatch.setattr(srv, "_deps", _fake_deps)
    return client


# ---------------------------------------------------------------------------
# list_tickets
# ---------------------------------------------------------------------------

@respx.mock
async def test_list_tickets_returns_shaped_items(patched_deps):
    from deskbridge.server import list_tickets
    respx.get(f"{BASE}/tickets").mock(
        return_value=httpx.Response(200, json=[FAKE_TICKET])
    )
    result = await list_tickets(per_page=10)
    assert result["count"] == 1
    assert result["page"] == 1
    item = result["items"][0]
    assert item["id"] == 101
    assert item["status_label"] == "Open"
    assert item["priority_label"] == "High"


@respx.mock
async def test_list_tickets_masks_pii_in_subject(patched_deps):
    from deskbridge.server import list_tickets
    respx.get(f"{BASE}/tickets").mock(
        return_value=httpx.Response(200, json=[FAKE_TICKET])
    )
    result = await list_tickets()
    subject = result["items"][0]["subject"]
    assert "@gmail.com" in subject          # domain retained
    assert "ravi.kumar" not in subject      # local part masked


@respx.mock
async def test_list_tickets_has_more_true_when_full_page(patched_deps):
    from deskbridge.server import list_tickets
    # Return exactly per_page items → has_more should be True
    tickets = [dict(FAKE_TICKET, id=i) for i in range(5)]
    respx.get(f"{BASE}/tickets").mock(
        return_value=httpx.Response(200, json=tickets)
    )
    result = await list_tickets(per_page=5)
    assert result["has_more"] is True


@respx.mock
async def test_list_tickets_has_more_false_when_partial_page(patched_deps):
    from deskbridge.server import list_tickets
    tickets = [dict(FAKE_TICKET, id=i) for i in range(3)]
    respx.get(f"{BASE}/tickets").mock(
        return_value=httpx.Response(200, json=tickets)
    )
    result = await list_tickets(per_page=5)
    assert result["has_more"] is False


@respx.mock
async def test_list_tickets_freshdesk_error_becomes_value_error(patched_deps, monkeypatch):
    from deskbridge.server import list_tickets
    respx.get(f"{BASE}/tickets").mock(return_value=httpx.Response(401))
    with pytest.raises(ValueError, match="401"):
        await list_tickets()


# ---------------------------------------------------------------------------
# get_ticket
# ---------------------------------------------------------------------------

@respx.mock
async def test_get_ticket_returns_conversations(patched_deps):
    from deskbridge.server import get_ticket
    respx.get(f"{BASE}/tickets/101").mock(
        return_value=httpx.Response(200, json=FAKE_TICKET)
    )
    result = await get_ticket(101)
    assert result["id"] == 101
    assert len(result["conversations"]) == 1
    conv = result["conversations"][0]
    assert conv["id"] == 201
    assert conv["incoming"] is True


@respx.mock
async def test_get_ticket_masks_pii_in_description_and_conversation(patched_deps):
    from deskbridge.server import get_ticket
    respx.get(f"{BASE}/tickets/101").mock(
        return_value=httpx.Response(200, json=FAKE_TICKET)
    )
    result = await get_ticket(101)
    desc = result["description"]
    assert "9876543210" not in desc          # phone masked
    body = result["conversations"][0]["body"]
    assert "test@example.com" not in body   # email masked


@respx.mock
async def test_get_ticket_without_conversations(patched_deps):
    from deskbridge.server import get_ticket
    respx.get(f"{BASE}/tickets/101").mock(
        return_value=httpx.Response(200, json=FAKE_TICKET)
    )
    result = await get_ticket(101, include_conversations=False)
    assert "conversations" not in result


@respx.mock
async def test_get_ticket_404_raises(patched_deps):
    from deskbridge.server import get_ticket
    respx.get(f"{BASE}/tickets/99999").mock(return_value=httpx.Response(404))
    with pytest.raises(ValueError, match="404"):
        await get_ticket(99999)


# ---------------------------------------------------------------------------
# search_tickets
# ---------------------------------------------------------------------------

SEARCH_RESPONSE = {
    "total": 1,
    "results": [FAKE_TICKET],
}


@respx.mock
async def test_search_tickets_returns_items(patched_deps):
    from deskbridge.server import search_tickets
    respx.get(f"{BASE}/search/tickets").mock(
        return_value=httpx.Response(200, json=SEARCH_RESPONSE)
    )
    result = await search_tickets(status=2)
    assert result["total_matches"] == 1
    assert result["items"][0]["id"] == 101


@respx.mock
async def test_search_tickets_passes_correct_query(patched_deps):
    from deskbridge.server import search_tickets
    route = respx.get(f"{BASE}/search/tickets").mock(
        return_value=httpx.Response(200, json={"total": 0, "results": []})
    )
    await search_tickets(status=2, priority=3)
    query_param = route.calls[0].request.url.params["query"]
    assert "status:2" in query_param
    assert "priority:3" in query_param


@respx.mock
async def test_search_tickets_no_filter_raises(patched_deps):
    from deskbridge.server import search_tickets
    with pytest.raises(ValueError, match="At least one filter"):
        await search_tickets()


async def test_search_tickets_page_over_10_raises(patched_deps):
    from deskbridge.server import search_tickets
    with pytest.raises(ValueError, match="10 pages"):
        await search_tickets(status=2, page=11)


@respx.mock
async def test_search_tickets_has_more_true(patched_deps):
    from deskbridge.server import search_tickets
    # 31 total matches, page 1 → has_more
    respx.get(f"{BASE}/search/tickets").mock(
        return_value=httpx.Response(200, json={"total": 31, "results": [FAKE_TICKET] * 30})
    )
    result = await search_tickets(status=2, page=1)
    assert result["has_more"] is True


@respx.mock
async def test_search_tickets_has_more_false_on_last_page(patched_deps):
    from deskbridge.server import search_tickets
    respx.get(f"{BASE}/search/tickets").mock(
        return_value=httpx.Response(200, json={"total": 31, "results": [FAKE_TICKET]})
    )
    result = await search_tickets(status=2, page=2)
    assert result["has_more"] is False

"""
DeskBridge MCP server.

Exposes three read-only tools to any MCP-compatible agent:
  - list_tickets   – paginated list of recent or updated tickets
  - get_ticket     – single ticket with optional conversation thread
  - search_tickets – filter by status, priority, tag, and/or date

Transport: stdio (stdout carries the MCP protocol; all logging goes to stderr).

IMPORTANT: Never print() in this file. Any stray bytes on stdout will break
the MCP framing. Use the `log` logger (stderr) for all diagnostics.
"""
import logging

from mcp.server.mcpserver import MCPServer as FastMCP

from .client import FreshdeskClient, FreshdeskError
from .config import Settings
from .models import shape_conversation, shape_ticket
from .search import build_query

# All log output goes to stderr, keeping stdout clean for the MCP protocol.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("deskbridge")

mcp = FastMCP(
    "deskbridge",
    instructions=(
        "Read-only Freshdesk connector. "
        "Use list_tickets to browse recent tickets, "
        "get_ticket to fetch a specific ticket with its replies, "
        "and search_tickets to filter by status/priority/tag/date. "
        "The connector never writes to Freshdesk and never returns more than "
        "300 search results or 10 conversations per ticket."
    ),
)

# Module-level singletons – initialised lazily on first tool call.
_settings: Settings | None = None
_client: FreshdeskClient | None = None


def _deps() -> tuple[Settings, FreshdeskClient]:
    """Return (settings, client), initialising them on the first call."""
    global _settings, _client
    if _client is None:
        _settings = Settings.from_env()
        _client = FreshdeskClient(_settings)
        log.info("FreshdeskClient ready (domain=%s, mask_pii=%s)",
                 _settings.domain, _settings.mask_pii)
    return _settings, _client  # type: ignore[return-value]


def _cap(n: int, cap: int) -> int:
    return max(1, min(n, cap))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_tickets(
    updated_since: str | None = None,
    requester_id: int | None = None,
    page: int = 1,
    per_page: int = 20,
    newest_first: bool = True,
) -> dict:
    """List Freshdesk tickets (read-only).

    Returns tickets created or updated in the last 30 days unless
    updated_since is supplied. Cannot filter by status/priority here;
    use search_tickets for that.

    Args:
        updated_since:  ISO date string (YYYY-MM-DD). Return only tickets
                        updated on or after this date.
        requester_id:   Freshdesk requester ID to filter by a single customer.
        page:           Page number (1-based).
        per_page:       Results per page (1–30, capped server-side).
        newest_first:   If True, most-recently updated tickets appear first.

    Returns:
        items:    List of ticket dicts (subject, status, priority, tags, etc.)
        page:     Current page number.
        count:    Number of items on this page.
        has_more: True if there are likely more pages available.
    """
    s, c = _deps()
    size = _cap(per_page, s.max_page_size)
    params: dict = {
        "page": max(1, page),
        "per_page": size,
        "order_type": "desc" if newest_first else "asc",
    }
    if updated_since:
        params["updated_since"] = updated_since.strip()
    if requester_id:
        params["requester_id"] = requester_id

    try:
        data = await c.get("/tickets", params)
    except FreshdeskError as exc:
        raise ValueError(str(exc)) from exc

    items = [shape_ticket(t, s.mask_pii) for t in data]
    return {
        "items": items,
        "page": params["page"],
        "count": len(items),
        "has_more": len(items) == size,
    }


@mcp.tool()
async def get_ticket(
    ticket_id: int,
    include_conversations: bool = True,
) -> dict:
    """Fetch one Freshdesk ticket by its numeric ID.

    Optionally includes up to 10 of the most recent replies and notes
    (conversation thread). Conversation bodies are truncated to 500 chars
    and have PII masked.

    Args:
        ticket_id:             The numeric Freshdesk ticket ID.
        include_conversations: If True, attach the conversation thread.

    Returns:
        A ticket dict plus, if requested, a 'conversations' list.
    """
    s, c = _deps()
    params = {"include": "conversations"} if include_conversations else None

    try:
        raw = await c.get(f"/tickets/{ticket_id}", params)
    except FreshdeskError as exc:
        raise ValueError(str(exc)) from exc

    out = shape_ticket(raw, s.mask_pii)
    if include_conversations:
        out["conversations"] = [
            shape_conversation(conv, s.mask_pii)
            for conv in raw.get("conversations", [])
        ]
    return out


@mcp.tool()
async def search_tickets(
    status: int | None = None,
    priority: int | None = None,
    tag: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    updated_after: str | None = None,
    page: int = 1,
) -> dict:
    """Search Freshdesk tickets using field filters (AND-combined).

    At least one filter must be provided. Free-text keyword search is not
    supported by the Freshdesk search API and is not exposed here.

    Freshdesk status codes:   2=Open, 3=Pending, 4=Resolved, 5=Closed
    Freshdesk priority codes: 1=Low, 2=Medium, 3=High, 4=Urgent

    Ceiling: 30 results per page × max 10 pages = 300 results per query.
    Narrow your filters if you need fewer results.

    Args:
        status:         Filter by status code (2–5).
        priority:       Filter by priority code (1–4).
        tag:            Filter by exact tag name (alphanumeric + space/dash/underscore).
        created_after:  YYYY-MM-DD – tickets created after this date.
        created_before: YYYY-MM-DD – tickets created before this date.
        updated_after:  YYYY-MM-DD – tickets updated after this date.
        page:           Page number (1–10).

    Returns:
        items:         List of ticket dicts.
        page:          Current page.
        total_matches: Total number of matching tickets (from Freshdesk).
        has_more:      True if more pages are available.
    """
    s, c = _deps()

    try:
        query = build_query(status, priority, tag, created_after, created_before, updated_after)
    except ValueError:
        raise  # already has a user-friendly message

    page = max(1, page)
    if page > 10:
        raise ValueError(
            "Freshdesk search supports at most 10 pages (300 results total). "
            "Please narrow your filters."
        )

    try:
        data = await c.get("/search/tickets", {"query": query, "page": page})
    except FreshdeskError as exc:
        raise ValueError(str(exc)) from exc

    results = data.get("results", [])
    total = data.get("total", len(results))
    items = [shape_ticket(t, s.mask_pii) for t in results]

    return {
        "items": items,
        "page": page,
        "total_matches": total,
        "has_more": page < 10 and (page * 30) < total,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()

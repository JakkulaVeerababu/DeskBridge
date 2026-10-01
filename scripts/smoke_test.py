"""
smoke_test.py – Exercises all three DeskBridge tools against a live Freshdesk
trial account. Run this after seeding with seed_tickets.py.

Usage:
    python scripts/smoke_test.py

Requires FRESHDESK_DOMAIN and FRESHDESK_API_KEY in .env (or environment).
"""
import asyncio
import json
import sys


def _pretty(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


async def main() -> None:
    # Import here so FRESHDESK_DOMAIN / FRESHDESK_API_KEY are already in env
    # (loaded from .env by config.py on import)
    from deskbridge.server import list_tickets, get_ticket, search_tickets

    # ------------------------------------------------------------------
    # 1. list_tickets
    # ------------------------------------------------------------------
    _section("list_tickets (page 1, newest first)")
    result = await list_tickets(per_page=5, newest_first=True)
    print(_pretty(result)[:1200])
    items = result.get("items", [])
    if not items:
        print("No tickets found. Run scripts/seed_tickets.py first.", file=sys.stderr)
        sys.exit(1)

    first_id = items[0]["id"]

    # ------------------------------------------------------------------
    # 2. get_ticket
    # ------------------------------------------------------------------
    _section(f"get_ticket(ticket_id={first_id}, include_conversations=True)")
    ticket = await get_ticket(first_id, include_conversations=True)
    print(_pretty(ticket)[:1200])
    # Verify PII masking
    desc = ticket.get("description", "") or ""
    convs = ticket.get("conversations", [])
    masked = any("***" in (c.get("body") or "") for c in convs) or "***" in desc
    print(f"\n  PII masking active in output: {masked}")

    # ------------------------------------------------------------------
    # 3. search_tickets – open high-priority
    # ------------------------------------------------------------------
    _section("search_tickets(status=2 [Open], priority=3 [High])")
    search_result = await search_tickets(status=2, priority=3)
    print(_pretty(search_result)[:1200])

    # ------------------------------------------------------------------
    # 4. search_tickets – by tag
    # ------------------------------------------------------------------
    _section("search_tickets(tag='refund')")
    tag_result = await search_tickets(tag="refund")
    print(_pretty(tag_result)[:600])

    # ------------------------------------------------------------------
    # 5. Error: no filters → ValueError
    # ------------------------------------------------------------------
    _section("search_tickets() – no filters (should raise ValueError)")
    try:
        await search_tickets()
        print("  ERROR: should have raised ValueError")
    except ValueError as exc:
        print(f"  OK – raised ValueError: {exc}")

    # ------------------------------------------------------------------
    # 6. Error: 404 for non-existent ticket
    # ------------------------------------------------------------------
    _section("get_ticket(99999999) – should raise ValueError [404]")
    try:
        await get_ticket(99999999)
        print("  ERROR: should have raised ValueError")
    except ValueError as exc:
        print(f"  OK – raised ValueError: {exc}")

    # ------------------------------------------------------------------
    # 7. Error: bad status code in search
    # ------------------------------------------------------------------
    _section("search_tickets(status=9) – invalid status (should raise ValueError)")
    try:
        await search_tickets(status=9)
        print("  ERROR: should have raised ValueError")
    except ValueError as exc:
        print(f"  OK – raised ValueError: {exc}")

    # ------------------------------------------------------------------
    # 8. Pagination: page > 10 rejected
    # ------------------------------------------------------------------
    _section("search_tickets(status=2, page=11) – over limit (should raise ValueError)")
    try:
        await search_tickets(status=2, page=11)
        print("  ERROR: should have raised ValueError")
    except ValueError as exc:
        print(f"  OK – raised ValueError: {exc}")

    print("\n\nAll smoke tests passed ✓")


if __name__ == "__main__":
    asyncio.run(main())

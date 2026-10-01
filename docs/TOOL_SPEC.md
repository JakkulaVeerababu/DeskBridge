# DeskBridge MCP Tool Specification

MCP server name: **`deskbridge`**  
Transport: **stdio**  
All tools are **read-only**. No mutations are possible.

---

## Shared data types

### Ticket object
| Field | Type | Description |
|---|---|---|
| `id` | integer | Freshdesk ticket ID |
| `subject` | string \| null | Ticket subject (PII-masked, max 200 chars) |
| `status` | integer | Numeric status code |
| `status_label` | string | Human-readable: Open, Pending, Resolved, Closed |
| `priority` | integer | Numeric priority code |
| `priority_label` | string | Human-readable: Low, Medium, High, Urgent |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |
| `due_by` | string \| null | ISO 8601 SLA due timestamp |
| `tags` | string[] | List of tag strings |
| `requester_id` | integer \| null | Freshdesk requester ID (not an email) |
| `description` | string \| null | Plain-text body (PII-masked, max 1 000 chars) |

### Conversation object (returned inside `get_ticket`)
| Field | Type | Description |
|---|---|---|
| `id` | integer | Conversation entry ID |
| `incoming` | boolean | True = message from customer; False = agent reply |
| `private` | boolean | True = internal note |
| `created_at` | string | ISO 8601 timestamp |
| `body` | string \| null | Plain-text body (PII-masked, max 500 chars) |

---

## Tool: `list_tickets`

List Freshdesk tickets, newest first by default.

### Input schema
```json
{
  "type": "object",
  "properties": {
    "updated_since": {
      "type": "string",
      "description": "YYYY-MM-DD – only return tickets updated on or after this date. Without this, Freshdesk returns only the last 30 days."
    },
    "requester_id": {
      "type": "integer",
      "description": "Filter by a specific Freshdesk requester ID."
    },
    "page": {
      "type": "integer",
      "default": 1,
      "description": "Page number (1-based)."
    },
    "per_page": {
      "type": "integer",
      "default": 20,
      "description": "Results per page. Capped at 30 server-side."
    },
    "newest_first": {
      "type": "boolean",
      "default": true,
      "description": "Order by updated_at descending."
    }
  }
}
```

### Output schema
```json
{
  "type": "object",
  "properties": {
    "items":    { "type": "array", "items": { "$ref": "#/Ticket" } },
    "page":     { "type": "integer" },
    "count":    { "type": "integer", "description": "Items on this page." },
    "has_more": { "type": "boolean", "description": "True if another page likely exists." }
  }
}
```

### Limitations
- Cannot filter by status or priority. Use `search_tickets` for that.
- Without `updated_since`, returns only tickets from the last 30 days.
- Page size capped at 30 regardless of `per_page` value.

---

## Tool: `get_ticket`

Fetch one ticket by numeric ID, optionally with its conversation thread.

### Input schema
```json
{
  "type": "object",
  "required": ["ticket_id"],
  "properties": {
    "ticket_id": {
      "type": "integer",
      "description": "Freshdesk ticket ID."
    },
    "include_conversations": {
      "type": "boolean",
      "default": true,
      "description": "If true, include the conversation thread (replies and notes)."
    }
  }
}
```

### Output schema
```json
{
  "$ref": "#/Ticket",
  "properties": {
    "conversations": {
      "type": "array",
      "items": { "$ref": "#/Conversation" },
      "description": "Present only when include_conversations is true. Max 10 entries."
    }
  }
}
```

### Limitations
- At most 10 most-recent conversations are returned.
- Attachments are not included.

---

## Tool: `search_tickets`

Filter tickets by structured field criteria. All active filters are AND-combined.

### Input schema
```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "integer",
      "enum": [2, 3, 4, 5],
      "description": "2=Open, 3=Pending, 4=Resolved, 5=Closed."
    },
    "priority": {
      "type": "integer",
      "enum": [1, 2, 3, 4],
      "description": "1=Low, 2=Medium, 3=High, 4=Urgent."
    },
    "tag": {
      "type": "string",
      "description": "Exact tag match. Alphanumeric + spaces/dashes/underscores, max 50 chars."
    },
    "created_after": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "YYYY-MM-DD – tickets created after this date."
    },
    "created_before": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "YYYY-MM-DD – tickets created before this date."
    },
    "updated_after": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "YYYY-MM-DD – tickets updated after this date."
    },
    "page": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10,
      "default": 1,
      "description": "Page number (1–10 only)."
    }
  }
}
```

At least one filter must be provided; calling with no arguments raises an error.

### Output schema
```json
{
  "type": "object",
  "properties": {
    "items":         { "type": "array", "items": { "$ref": "#/Ticket" } },
    "page":          { "type": "integer" },
    "total_matches": { "type": "integer", "description": "Total matched tickets (from Freshdesk)." },
    "has_more":      { "type": "boolean" }
  }
}
```

### Limitations
- Free-text search is not supported; field-equality and date-range filters only.
- At most 30 results per page × 10 pages = **300 results maximum per query**.
- Tag matching is exact; partial tag matches are not possible.

---

## Error behaviour

All tools raise a `ValueError` with a human-readable message on failure.

| Situation | Message pattern |
|---|---|
| Missing env vars | `Set FRESHDESK_DOMAIN and FRESHDESK_API_KEY (see .env.example)` |
| Bad API key | `[401] authentication failed: check FRESHDESK_API_KEY and FRESHDESK_DOMAIN` |
| Ticket not found | `[404] not found` |
| Rate limit exhausted | `[429] rate limit: retries exhausted` |
| Invalid filter value | `status must be one of 2 (open), 3 (pending), 4 (resolved), 5 (closed); got 9` |
| No filters supplied | `At least one filter is required (status, priority, tag, or a date range)` |
| Page > 10 | `Freshdesk search supports at most 10 pages (300 results total). Please narrow your filters.` |

---

## How to dump the live schema

After installing the package, run:

```bash
python -c "
import asyncio, json
from deskbridge.server import mcp
tools = asyncio.run(mcp.list_tools())
print(json.dumps([t.model_dump() for t in tools], indent=2, default=str))
"
```

This prints the exact JSON schemas FastMCP generates from the type hints in `server.py`.

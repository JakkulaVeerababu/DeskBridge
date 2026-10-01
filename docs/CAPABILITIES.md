# DeskBridge Capabilities

What the agent **can** and **cannot** do when using the DeskBridge connector.

---

## What the agent CAN do

| Capability | Tool | Notes |
|---|---|---|
| List recent tickets, newest first | `list_tickets` | Last 30 days unless `updated_since` is supplied |
| Filter list by update date | `list_tickets` | `updated_since: "YYYY-MM-DD"` |
| Filter list by requester | `list_tickets` | Freshdesk requester ID (integer) |
| Paginate results | `list_tickets` | Up to 30 per page |
| Fetch one ticket by ID | `get_ticket` | Returns full ticket + conversation thread |
| Read conversation thread | `get_ticket` | Up to 10 most-recent replies and notes |
| Search by status | `search_tickets` | 2=Open, 3=Pending, 4=Resolved, 5=Closed |
| Search by priority | `search_tickets` | 1=Low, 2=Medium, 3=High, 4=Urgent |
| Search by exact tag | `search_tickets` | Alphanumeric, space, dash, underscore; max 50 chars |
| Search by date range | `search_tickets` | `created_after/before`, `updated_after` in YYYY-MM-DD |
| Combine search filters | `search_tickets` | All active filters AND-combined |
| Survive rate limiting | All tools | Waits on HTTP 429 Retry-After (max 60 s); backs off on 5xx and network errors |
| Mask emails and phone numbers | All tools | Enabled by default; controlled by `DESKBRIDGE_MASK_PII` env var |

---

## What the agent CANNOT do

| Limitation | Reason |
|---|---|
| **Create, update, or close tickets** | Connector is strictly read-only by design. No write tools exist. |
| **Reply or add notes to a ticket** | Same – no write tools. |
| **Free-text / keyword search** | Freshdesk's search API accepts only field-equality and range operators, not full-text search. |
| **Return more than 300 search results** | Freshdesk search caps at 30 results/page × 10 pages. Narrow filters to stay within this. |
| **List tickets older than 30 days** | Freshdesk `GET /tickets` default window; supply `updated_since` to go back further. |
| **Filter `list_tickets` by status or priority** | The list endpoint doesn't support these; use `search_tickets` instead. |
| **Return more than 10 conversations per ticket** | Freshdesk `include=conversations` returns the 10 most-recent only. |
| **Read attachments** | Not exposed; would require separate authenticated downloads. |
| **Read contacts, companies, or knowledge-base articles** | Out of scope for this connector. |
| **Guarantee complete PII removal** | Masking is regex-based; it catches common email and phone patterns but misses names, addresses, and unusual formats. See "Production path" below. |
| **Support per-user (OAuth) auth** | Uses a single API key shared across all agent invocations. |
| **Cache results** | Every tool call hits the Freshdesk API. |

---

## Assumptions

1. One Freshdesk account per server instance.
2. The API key has agent-level read permission on all tickets.
3. The `FRESHDESK_DOMAIN` is the subdomain only (e.g., `acme`, not `acme.freshdesk.com`).
4. Python ≥ 3.10 is available in the environment running the server.

---

## Known limitations and the production-grade fix

### 300-result search ceiling
**Why it exists:** Freshdesk's search API is paginated at 30 results/page with a hard 10-page limit.  
**Workaround:** Narrow date windows or add a tag/status filter to reduce the result set.  
**Long-term fix:** Sync tickets into a local index (e.g., Elasticsearch or a Postgres full-text index) via Freshdesk webhooks. The agent queries the local index, removing the 300-result cap and enabling real full-text search.

### Regex PII masking
**Why it's limited:** The regex catches common email addresses and phone numbers but not names, street addresses, national IDs, or unusual phone formats (e.g., extensions, shortcodes).  
**Long-term fix:** Route all free text through a proper PII detection service (e.g., Google Cloud DLP, AWS Comprehend PII detection) before returning to the agent. Alternatively, configure Freshdesk-side contact-data policies to redact fields at source.

### Shared API key
**Why it's limited:** All agent invocations share the same key. If the key is rotated or revoked, all connections fail simultaneously. Rate limit is also shared with any other tool using the same key.  
**Long-term fix:** Store per-merchant credentials in a secrets manager (e.g., HashiCorp Vault, AWS Secrets Manager). Implement a shared token-bucket rate limiter rather than purely reactive 429 handling.

### No caching
**Why it matters:** Repeated reads of the same ticket cost API calls, which counts against the rate limit.  
**Long-term fix:** Short-lived TTL cache (Redis or in-process) keyed by ticket ID and query hash. Invalidated by webhooks on ticket update.

### Audit trail
**Why it matters:** In a production merchant-facing deployment, every agent read should be logged with the merchant ID, tool name, parameters, and timestamp.  
**Long-term fix:** Structured audit log per read operation, stored separately from application logs.

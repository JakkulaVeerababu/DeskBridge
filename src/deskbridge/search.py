"""
Freshdesk search query builder.

Builds the ?query="..." string for /api/v2/search/tickets from validated
individual fields. The agent never passes raw query text, so it cannot
inject Freshdesk query operators or escape the quotes.

Freshdesk status codes: 2=Open, 3=Pending, 4=Resolved, 5=Closed
Freshdesk priority codes: 1=Low, 2=Medium, 3=High, 4=Urgent
"""
import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAG = re.compile(r"^[A-Za-z0-9_\- ]{1,50}$")

_VALID_STATUS = frozenset((2, 3, 4, 5))
_VALID_PRIORITY = frozenset((1, 2, 3, 4))


def build_query(
    status: int | None = None,
    priority: int | None = None,
    tag: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    updated_after: str | None = None,
) -> str:
    """
    Return a Freshdesk search query string with outer double-quotes included.

    All clauses are AND-combined. At least one argument must be provided.
    Raises ValueError for invalid inputs.
    """
    parts: list[str] = []

    if status is not None:
        if status not in _VALID_STATUS:
            raise ValueError(
                f"status must be one of 2 (open), 3 (pending), 4 (resolved), 5 (closed); "
                f"got {status!r}"
            )
        parts.append(f"status:{status}")

    if priority is not None:
        if priority not in _VALID_PRIORITY:
            raise ValueError(
                f"priority must be one of 1 (low), 2 (medium), 3 (high), 4 (urgent); "
                f"got {priority!r}"
            )
        parts.append(f"priority:{priority}")

    if tag is not None:
        tag = tag.strip()
        if not _TAG.match(tag):
            raise ValueError(
                "tag may only contain letters, digits, spaces, underscores, and hyphens "
                "(1–50 chars)"
            )
        parts.append(f"tag:'{tag}'")

    for field, op, value in (
        ("created_at", ">", created_after),
        ("created_at", "<", created_before),
        ("updated_at", ">", updated_after),
    ):
        if value is not None:
            value = value.strip()
            if not _DATE.match(value):
                raise ValueError(
                    f"Date for '{field}' must be in YYYY-MM-DD format; got {value!r}"
                )
            parts.append(f"{field}:{op}'{value}'")

    if not parts:
        raise ValueError(
            "At least one filter is required (status, priority, tag, or a date range)"
        )

    return '"' + " AND ".join(parts) + '"'

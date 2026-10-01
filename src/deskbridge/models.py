"""
Shape raw Freshdesk API responses into clean, agent-friendly dicts.

Only whitelisted fields are forwarded. PII in text fields is masked
via pii.mask_text before being returned to the agent.
"""
from .pii import mask_text

# Freshdesk numeric → human-readable label maps
STATUS_LABEL: dict[int, str] = {
    2: "Open",
    3: "Pending",
    4: "Resolved",
    5: "Closed",
}
PRIORITY_LABEL: dict[int, str] = {
    1: "Low",
    2: "Medium",
    3: "High",
    4: "Urgent",
}


def shape_ticket(raw: dict, mask: bool) -> dict:
    """
    Return a trimmed ticket dict suitable for agent consumption.

    Fields included (all others are dropped):
        id, subject, status/label, priority/label,
        created_at, updated_at, due_by, tags, requester_id, description
    """
    status = raw.get("status")
    priority = raw.get("priority")
    return {
        "id": raw.get("id"),
        "subject": mask_text(raw.get("subject"), mask, limit=200),
        "status": status,
        "status_label": STATUS_LABEL.get(status, "Other"),
        "priority": priority,
        "priority_label": PRIORITY_LABEL.get(priority, "Other"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "due_by": raw.get("due_by"),
        "tags": raw.get("tags", []),
        "requester_id": raw.get("requester_id"),
        # description_text is plain text; description is HTML – prefer the former
        "description": mask_text(
            raw.get("description_text") or raw.get("description"), mask, limit=1000
        ),
    }


def shape_conversation(raw: dict, mask: bool) -> dict:
    """
    Return a trimmed conversation entry (reply or note).

    Fields included:
        id, incoming, private, created_at, body (plain text, masked)
    """
    return {
        "id": raw.get("id"),
        "incoming": raw.get("incoming"),
        "private": raw.get("private"),
        "created_at": raw.get("created_at"),
        # body_text is plain text; body is HTML
        "body": mask_text(
            raw.get("body_text") or raw.get("body"), mask, limit=500
        ),
    }

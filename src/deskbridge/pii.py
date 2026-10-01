"""
PII masking utilities.

Uses regex to detect and partially mask email addresses and phone numbers
in text fields before they are returned to the agent.

Limitations (documented in docs/CAPABILITIES.md):
  - Regex-based: can miss names, street addresses, and unusual phone formats.
  - Does not strip structured fields like requester_id (those stay as IDs).
  - Not a substitute for a proper PII service in production.
"""
import re

# Match emails: keep first char of local part + domain
_EMAIL = re.compile(
    r"([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*"
    r"@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)

# Match phone-like sequences: 9+ digits, optionally separated by spaces/hyphens
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s\-]{7,}\d)(?!\d)")


def mask_text(text: str | None, enabled: bool = True, limit: int = 1000) -> str | None:
    """
    Mask PII in *text* and truncate to *limit* chars.

    When *enabled* is False the text is still truncated but PII is kept,
    which is useful for debugging against a private trial account.
    """
    if text is None:
        return None
    if enabled:
        # Email: first char of local part + *** + @domain
        text = _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
        # Phone: keep only last two digits of the digit string
        text = _PHONE.sub(
            lambda m: "***" + re.sub(r"\D", "", m.group(1))[-2:], text
        )
    if len(text) > limit:
        text = text[:limit] + "…[truncated]"
    return text

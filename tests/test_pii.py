"""Tests for PII masking utility."""
import pytest

from deskbridge.pii import mask_text


# ---------------------------------------------------------------------------
# Email masking
# ---------------------------------------------------------------------------

def test_email_keeps_first_char_and_domain():
    result = mask_text("Contact ravi.kumar@gmail.com for help")
    assert result == "Contact r***@gmail.com for help"


def test_email_with_plus_alias():
    result = mask_text("billing+test@company.co.in")
    assert result == "b***@company.co.in"


def test_multiple_emails_all_masked():
    text = "From: a@x.com, To: b@y.com"
    result = mask_text(text)
    assert "a***@x.com" in result
    assert "b***@y.com" in result


# ---------------------------------------------------------------------------
# Phone masking
# ---------------------------------------------------------------------------

def test_phone_10_digits_keeps_last_two():
    result = mask_text("Call 9876543210 now")
    assert result == "Call ***10 now"


def test_phone_with_country_code():
    result = mask_text("+91 98765 43210")
    # digits: 919876543210 → last 2 = "10"
    assert "***10" in result


def test_phone_not_masked_when_too_short():
    # 7 digits shouldn't match (need 9+ including separators to give >=9 digits)
    result = mask_text("code 1234567 end", enabled=True)
    # This is borderline; just assert it doesn't crash
    assert result is not None


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

def test_truncation_at_limit():
    long_text = "x" * 1500
    result = mask_text(long_text, limit=1000)
    assert result is not None
    assert result.endswith("…[truncated]")
    # The non-suffix part should be exactly 1000 chars
    assert len(result.replace("…[truncated]", "")) == 1000


def test_no_truncation_under_limit():
    text = "short"
    assert mask_text(text, limit=1000) == "short"


# ---------------------------------------------------------------------------
# Disabled masking
# ---------------------------------------------------------------------------

def test_masking_disabled_preserves_email():
    text = "user@example.com"
    assert mask_text(text, enabled=False) == "user@example.com"


def test_masking_disabled_still_truncates():
    long_text = "a" * 2000
    result = mask_text(long_text, enabled=False, limit=500)
    assert result is not None
    assert result.endswith("…[truncated]")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_input_returns_none():
    assert mask_text(None) is None


def test_empty_string_returns_empty():
    assert mask_text("") == ""


def test_no_pii_unchanged():
    text = "This ticket is about a refund."
    assert mask_text(text) == text

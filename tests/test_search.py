"""Tests for Freshdesk search query builder."""
import pytest

from deskbridge.search import build_query


# ---------------------------------------------------------------------------
# Valid inputs
# ---------------------------------------------------------------------------

def test_status_only():
    assert build_query(status=2) == '"status:2"'


def test_priority_only():
    assert build_query(priority=1) == '"priority:1"'


def test_tag_only():
    assert build_query(tag="refund") == '"tag:\'refund\'"'


def test_tag_with_spaces():
    assert build_query(tag="payment link") == '"tag:\'payment link\'"'


def test_created_after_only():
    assert build_query(created_after="2026-09-01") == '"created_at:>\'2026-09-01\'"'


def test_created_before_only():
    assert build_query(created_before="2026-09-30") == '"created_at:<\'2026-09-30\'"'


def test_updated_after_only():
    assert build_query(updated_after="2026-08-01") == '"updated_at:>\'2026-08-01\'"'


def test_combined_status_and_priority():
    q = build_query(status=2, priority=3)
    assert q == '"status:2 AND priority:3"'


def test_combined_all_filters():
    q = build_query(
        status=2,
        priority=3,
        tag="refund",
        created_after="2026-09-01",
        created_before="2026-09-30",
        updated_after="2026-08-01",
    )
    assert "status:2" in q
    assert "priority:3" in q
    assert "tag:'refund'" in q
    assert "created_at:>'2026-09-01'" in q
    assert "created_at:<'2026-09-30'" in q
    assert "updated_at:>'2026-08-01'" in q
    # All parts AND-combined
    assert " AND " in q
    # Wrapped in double quotes
    assert q.startswith('"') and q.endswith('"')


# ---------------------------------------------------------------------------
# Invalid status
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_status", [0, 1, 6, 99, -1])
def test_rejects_invalid_status(bad_status):
    with pytest.raises(ValueError, match="status"):
        build_query(status=bad_status)


# ---------------------------------------------------------------------------
# Invalid priority
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_priority", [0, 5, -1, 100])
def test_rejects_invalid_priority(bad_priority):
    with pytest.raises(ValueError, match="priority"):
        build_query(priority=bad_priority)


# ---------------------------------------------------------------------------
# Invalid tag (injection attempt)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_tag", [
    "x' OR 1:1",          # SQL-style injection
    "tag\"; DROP TABLE",  # another injection attempt
    "",                   # empty
    "a" * 51,             # too long
    "tag!@#",             # special chars
])
def test_rejects_invalid_tag(bad_tag):
    with pytest.raises(ValueError):
        build_query(tag=bad_tag)


# ---------------------------------------------------------------------------
# Invalid date formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_date", [
    "01/09/2026",    # DD/MM/YYYY
    "2026/09/01",    # wrong separator
    "09-01-2026",    # MM-DD-YYYY
    "2026-9-1",      # missing zero-padding
    "not-a-date",
])
def test_rejects_invalid_created_after(bad_date):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        build_query(created_after=bad_date)


def test_rejects_invalid_created_before():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        build_query(created_before="2026.09.30")


def test_rejects_invalid_updated_after():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        build_query(updated_after="yesterday")


# ---------------------------------------------------------------------------
# No filters at all
# ---------------------------------------------------------------------------

def test_no_filters_raises():
    with pytest.raises(ValueError, match="At least one filter"):
        build_query()

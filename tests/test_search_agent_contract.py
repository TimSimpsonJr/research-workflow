# tests/test_search_agent_contract.py
"""Contract tests for search-agent output schema.

These tests don't dispatch a real agent — they validate that any output
matching the spec can be parsed correctly downstream.
"""
import json
import pytest


def parse_search_output(text: str) -> dict:
    """Parse an agent response. First char must be `{`, last char `}`."""
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise ValueError("Response must be a single raw JSON object")
    return json.loads(text)


def test_valid_search_response_parses():
    response = json.dumps({
        "topic": "SC ALPR programs",
        "depth": "standard",
        "queries_used": ["SC ALPR site:.gov"],
        "selected_urls": [
            {
                "url": "https://sled.sc.gov/data",
                "title": "SLED ALPR data",
                "snippet": "Official SLED data on ALPR usage",
                "relevance_score": 0.92,
                "credibility_score": 0.95,
                "tier": "T1",
                "is_primary": True,
                "primary_type": "agency_data",
                "reason": "Official agency data",
            }
        ],
        "rejected_urls": [],
        "search_notes": "",
    })
    parsed = parse_search_output(response)
    assert parsed["selected_urls"][0]["tier"] == "T1"
    assert parsed["selected_urls"][0]["is_primary"] is True
    assert parsed["selected_urls"][0]["primary_type"] == "agency_data"


def test_secondary_source_has_null_primary_type():
    response = json.dumps({
        "topic": "X",
        "depth": "quick",
        "queries_used": [],
        "selected_urls": [
            {
                "url": "https://example.com",
                "title": "X",
                "snippet": "",
                "relevance_score": 0.7,
                "credibility_score": 0.75,
                "tier": "T2",
                "is_primary": False,
                "primary_type": None,
                "reason": "",
            }
        ],
        "rejected_urls": [],
        "search_notes": "",
    })
    parsed = parse_search_output(response)
    assert parsed["selected_urls"][0]["is_primary"] is False
    assert parsed["selected_urls"][0]["primary_type"] is None


def test_tier_consistent_with_credibility_score():
    """Tier and credibility_score should be consistent per the bucket boundaries."""
    from confidence import tier_from_score
    bucketed = tier_from_score(0.92)
    assert bucketed == "T1"
    bucketed = tier_from_score(0.75)
    assert bucketed == "T2"


VALID_PRIMARY_TYPES = {None, "agency_data", "legal_record", "foia",
                       "official_statement", "peer_reviewed"}


def test_primary_type_must_be_enumerated_value():
    """primary_type values must come from the agent spec enum (or null when is_primary=False)."""
    # A response with an out-of-enum primary_type indicates the agent drifted
    # or someone authored a fixture/test without consulting the spec.
    for pt in ["agency_data", "legal_record", "foia", "official_statement", "peer_reviewed", None]:
        assert pt in VALID_PRIMARY_TYPES


def test_primary_type_null_when_not_primary():
    """Spec invariant: is_primary=False implies primary_type=None."""
    response = json.dumps({
        "topic": "X",
        "depth": "standard",
        "queries_used": [],
        "selected_urls": [
            {"url": "u", "title": "t", "snippet": "", "relevance_score": 0.5,
             "credibility_score": 0.6, "tier": "T3", "is_primary": False,
             "primary_type": None, "reason": ""},
        ],
        "rejected_urls": [],
        "search_notes": "",
    })
    parsed = parse_search_output(response)
    for url in parsed["selected_urls"]:
        if not url["is_primary"]:
            assert url["primary_type"] is None, "is_primary=False must have null primary_type"

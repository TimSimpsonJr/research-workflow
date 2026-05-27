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

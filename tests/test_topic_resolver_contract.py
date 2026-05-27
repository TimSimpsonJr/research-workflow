import json
import pytest


def test_planning_only_response():
    response = json.dumps({
        "project": "SC H.3456 Research",
        "strategy": "planning_only",
        "shared_context_files": [],
        "topics": [
            {
                "topic": "SC bill H.3456",
                "mode": "web_research",
                "depth": "standard",
                "existing_urls": [],
                "related_vault_notes": [],
            }
        ],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    assert parsed["strategy"] == "planning_only"
    assert parsed["topics"][0]["depth"] == "standard"
    assert "priority" not in parsed["topics"][0]


def test_intent_planning_response():
    response = json.dumps({
        "strategy": "intent_planning",
        "clarifying_questions": [
            "Which state are you focused on?",
            "Are you looking for legislative analysis or political angle?",
        ],
        "project": "",
        "topics": [],
        "local_sources": [],
        "thread_pulls": [],
    })
    parsed = json.loads(response)
    assert parsed["strategy"] == "intent_planning"
    assert len(parsed["clarifying_questions"]) <= 3


def test_depth_value_in_response_is_valid():
    """A topic's depth field must be one of the four valid profile names."""
    response = json.dumps({
        "project": "X",
        "strategy": "planning_only",
        "shared_context_files": [],
        "topics": [{"topic": "T", "mode": "web_research", "depth": "standard",
                    "existing_urls": [], "related_vault_notes": []}],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    valid_depths = {"quick", "standard", "deep", "exhaustive"}
    for topic in parsed["topics"]:
        assert topic["depth"] in valid_depths, f"invalid depth: {topic['depth']!r}"


def test_strategy_value_is_valid():
    """Top-level strategy must be one of three values; rejects malformed responses."""
    response = json.dumps({
        "project": "X",
        "strategy": "unified",
        "shared_context_files": [],
        "topics": [],
        "local_sources": [],
        "thread_pulls": [],
        "execution_order": "parallel",
        "estimated_usage": {},
    })
    parsed = json.loads(response)
    valid_strategies = {"planning_only", "intent_planning", "unified"}
    assert parsed["strategy"] in valid_strategies, f"invalid strategy: {parsed['strategy']!r}"

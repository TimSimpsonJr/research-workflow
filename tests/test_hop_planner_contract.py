import json


def test_hop_planner_continue_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 2,
        "decision": "continue",
        "confidence_score": 0.68,
        "contradiction_rate": 0.22,
        "next_hop": {
            "pattern": "causal_chain",
            "from": "federal data sharing",
            "rationale": "...",
            "candidate_score": {"frequency": 3, "novelty": 3, "connectedness": 1, "specificity": 2, "total": 9},
            "runner_up_alternatives": [],
        },
        "self_reflection": "...",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "continue"
    assert parsed["next_hop"]["pattern"] in {
        "entity_expansion", "temporal_progression", "conceptual_deepening", "causal_chain"
    }


def test_hop_planner_stop_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 3,
        "decision": "stop",
        "confidence_score": 0.82,
        "contradiction_rate": 0.1,
        "next_hop": None,
        "self_reflection": "Confidence target met.",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "stop"
    assert parsed["next_hop"] is None


def test_hop_planner_replan_response():
    response = json.dumps({
        "topic": "X",
        "current_hop": 1,
        "decision": "replan",
        "confidence_score": 0.31,
        "contradiction_rate": 0.0,
        "replan_hint": {
            "issue": "initial search returned only T3 sources",
            "suggested_pattern": "entity_expansion",
            "suggested_query_focus": "official agency data",
        },
        "self_reflection": "...",
    })
    parsed = json.loads(response)
    assert parsed["decision"] == "replan"
    assert "replan_hint" in parsed

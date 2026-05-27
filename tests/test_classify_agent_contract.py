import json


def test_classify_output_has_contradictions_field():
    response = json.dumps({
        "topic": "X",
        "notes_to_create": [],
        "vault_context": {"existing_notes_found": [], "suggested_moc_update": None,
                          "folder_conventions": {}},
        "contradictions_detected": [],
    })
    parsed = json.loads(response)
    assert "contradictions_detected" in parsed
    assert isinstance(parsed["contradictions_detected"], list)


def test_classify_contradiction_shape():
    response = json.dumps({
        "topic": "X",
        "notes_to_create": [],
        "vault_context": {"existing_notes_found": [], "suggested_moc_update": None,
                          "folder_conventions": {}},
        "contradictions_detected": [
            {
                "claim_a": "A",
                "claim_b": "B",
                "source_a": "url_a",
                "source_b": "url_b",
                "tier_a": "T1",
                "tier_b": "T2",
                "nature": "factual",
            }
        ],
    })
    parsed = json.loads(response)
    c = parsed["contradictions_detected"][0]
    assert {"claim_a", "claim_b", "source_a", "source_b", "tier_a", "tier_b", "nature"} <= c.keys()
    assert c["nature"] in {"factual", "interpretive", "temporal", "jurisdictional"}

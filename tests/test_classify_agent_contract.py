import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "research_integration"

# Required fields for each note in notes_to_create[], per agents/classify-agent.md
# Output spec. Stage 7 (Write Notes) and the spec's "Field notes" section both
# depend on these being present.
NOTE_REQUIRED_FIELDS = {
    "title",
    "filename",
    "folder",
    "action",
    "type",
    "write_model",
    "content_summary",
    "source_urls",
    "tags",
    "links",
    "stub_links",
    "media",
    "priority",
}


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


def test_classify_fixture_has_all_note_required_fields():
    """The research_integration fixture must exercise every required note field.

    Without this, the fixture can drift away from the agent spec and downstream
    tests that load it will pass even when the contract is silently broken.
    """
    fixture = json.loads((FIXTURE_DIR / "classify_response.json").read_text())
    assert fixture["notes_to_create"], "fixture must contain at least one note"
    for note in fixture["notes_to_create"]:
        missing = NOTE_REQUIRED_FIELDS - note.keys()
        assert not missing, f"note missing required fields: {missing}"


def test_classify_fixture_field_types():
    """Type-check the fixture's note fields against the agent spec."""
    fixture = json.loads((FIXTURE_DIR / "classify_response.json").read_text())
    for note in fixture["notes_to_create"]:
        assert isinstance(note["title"], str)
        assert isinstance(note["filename"], str) and note["filename"].endswith(".md")
        assert isinstance(note["folder"], str)
        assert note["action"] in {"create", "update"}
        assert isinstance(note["type"], str)
        assert note["write_model"] in {"sonnet", "opus"}
        assert isinstance(note["content_summary"], str)
        assert isinstance(note["source_urls"], list)
        assert isinstance(note["tags"], list)
        assert isinstance(note["links"], list)
        assert isinstance(note["stub_links"], list)
        assert isinstance(note["media"], list)
        assert note["priority"] in {"primary", "secondary", "scan"}

import json
import subprocess
from unittest.mock import patch


def test_haiku_dispatch_request_shape():
    """When orchestrator dispatches case-analyzer, the request payload includes
    both CANDIDATE and EXISTING blocks."""
    captured_prompt = {}

    def fake_run(*args, **kwargs):
        if "input" in kwargs:
            captured_prompt["prompt"] = kwargs["input"]
        class R:
            returncode = 0
            stdout = json.dumps({"is_same": False, "reason": "mock"})
            stderr = ""
        return R()

    from case_analyzer import dispatch_semantic_compare
    with patch("subprocess.run", side_effect=fake_run):
        result = dispatch_semantic_compare(
            candidate_body="T1 sources dominate for civic ALPR queries.",
            existing_body="Government sites win out for civic ALPR research.",
            timeout_s=5,
        )
    assert "CANDIDATE" in captured_prompt["prompt"]
    assert "EXISTING" in captured_prompt["prompt"]
    assert result["is_same"] is False


def test_haiku_dispatch_timeout_returns_conservative_distinct():
    """On timeout, dispatch_semantic_compare returns is_same=False with a warning."""
    from case_analyzer import dispatch_semantic_compare
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=5)
    with patch("subprocess.run", side_effect=fake_run):
        result = dispatch_semantic_compare(
            candidate_body="x",
            existing_body="y",
            timeout_s=5,
        )
    assert result["is_same"] is False
    assert "timeout" in result.get("reason", "").lower()

def test_compute_run_outcome_win():
    """Win: avg confidence >= target, no abandon, contradiction_rate <= 0.3."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82, "t2": 0.78},
        "contradiction_rate": 0.15,
        "outcomes": {"user_decisions": [{"stage": "5", "choice": "accept"}]},
        "depths_used": {"standard": 2},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "W"


def test_compute_run_outcome_loss_low_confidence():
    """Loss: avg confidence below target."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.55, "t2": 0.6},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": []},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"


def test_compute_run_outcome_loss_user_abandoned():
    """Loss: user picked 'abandon' at quality gate."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.1,
        "outcomes": {"user_decisions": [{"stage": "5", "choice": "abandon"}]},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"


def test_compute_run_outcome_loss_contradiction_spike():
    """Loss: contradiction_rate > 0.3."""
    from score_updates import compute_run_outcome
    case = {
        "confidence_per_topic": {"t1": 0.82},
        "contradiction_rate": 0.45,
        "outcomes": {"user_decisions": []},
    }
    assert compute_run_outcome(case, confidence_target=0.75) == "L"

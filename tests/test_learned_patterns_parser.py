from learned_patterns import (
    LearnedPattern,
    LearnedPatternsFile,
    LEARNED_PATTERNS_SCHEMA_VERSION,
    load_learned_patterns,
    save_learned_patterns,
)


def test_load_missing_returns_empty(tmp_path):
    """Missing file returns empty LearnedPatternsFile with no warnings."""
    loaded, warnings = load_learned_patterns(tmp_path / "missing.md")
    assert loaded.version == LEARNED_PATTERNS_SCHEMA_VERSION
    assert loaded.patterns == []
    assert warnings == []


def test_save_then_load_roundtrip(tmp_path):
    """Round-trip preserves all fields and grouping; no warnings on clean load."""
    target = tmp_path / "learned_patterns.md"
    file = LearnedPatternsFile(
        version=LEARNED_PATTERNS_SCHEMA_VERSION,
        patterns=[
            LearnedPattern(
                id="civic-alpr-t1-dominance-3f7a",
                name="T1 sources dominate",
                body="T1 sources dominate: government sites, fusion center reports, ACLU policy memos.",
                domain_tags=["civic", "alpr"],
                target_stage="search",
                category="source-tier-bias",
                wins=12, losses=1,
                promoted_at="2026-04-15",
                demotion_count=0,
            ),
            LearnedPattern(
                id="civic-alpr-entity-h2-9c2b",
                name="entity_expansion at hop 2",
                body="typically lifts confidence 0.5->0.75 for SC topics.",
                domain_tags=["civic", "alpr"],
                target_stage="hop_planner",
                category="hop-pattern-bias",
                wins=5, losses=1,
                promoted_at="2026-05-02",
                demotion_count=0,
            ),
        ],
    )
    save_learned_patterns(target, file)
    loaded, warnings = load_learned_patterns(target)
    assert loaded == file
    assert warnings == []


def test_load_version_mismatch_returns_empty_with_warning(tmp_path):
    """Schema version mismatch returns empty file + warning."""
    target = tmp_path / "learned_patterns.md"
    target.write_text("---\nversion: 99\n---\n\n## civic\n\n### Search patterns\n\n- **X** — body.\n  - id: `x`\n  - score: 1W / 0L (1 uses)\n  - promoted: 2026-04-15\n  - demotions: 0\n", encoding="utf-8")
    loaded, warnings = load_learned_patterns(target)
    assert loaded.patterns == []
    assert len(warnings) == 1
    assert "learned_patterns_schema_mismatch" in warnings[0]


def test_parse_skips_malformed_entry_missing_id(tmp_path, capsys):
    """Entry missing `id:` line is skipped; valid entries still parsed."""
    body = """---
version: 1
---

## civic / alpr

### Search patterns

- **Good entry** — has all fields.
  - id: `good-1`
  - score: 5W / 0L (5 uses)
  - promoted: 2026-04-15
  - demotions: 0

- **Bad entry** — missing id.
  - score: 1W / 0L (1 uses)
  - promoted: 2026-05-01
  - demotions: 0
"""
    target = tmp_path / "learned_patterns.md"
    target.write_text(body, encoding="utf-8")
    loaded, _warnings = load_learned_patterns(target)
    assert len(loaded.patterns) == 1
    assert loaded.patterns[0].id == "good-1"


def test_parse_recovers_score_line(tmp_path):
    """Score line `score: 12W / 1L (13 uses)` parses to wins=12, losses=1."""
    body = """---
version: 1
---

## civic / alpr

### Search patterns

- **Entry** — body text.
  - id: `e1`
  - score: 12W / 1L (13 uses)
  - promoted: 2026-04-15
  - demotions: 2
"""
    p = tmp_path / "lp.md"
    p.write_text(body, encoding="utf-8")
    loaded, _warnings = load_learned_patterns(p)
    assert len(loaded.patterns) == 1
    p0 = loaded.patterns[0]
    assert p0.wins == 12
    assert p0.losses == 1
    assert p0.demotion_count == 2


def test_load_invalid_utf8_returns_empty_with_warning(tmp_path):
    """Invalid UTF-8 returns empty file + warning, never raises (parity with load_accumulator)."""
    target = tmp_path / "learned_patterns.md"
    target.write_bytes(b"\xff\xfe invalid utf-8 \xff")
    loaded, warnings = load_learned_patterns(target)
    assert loaded.patterns == []
    assert len(warnings) == 1
    assert "learned_patterns_corrupted" in warnings[0]


def test_filter_by_topic_text_substring_match():
    """filter_by_topic_text matches patterns whose domain_tags appear as
    case-insensitive substrings in the joined topic text. Used at Stage 2
    where formal domain_tags don't yet exist."""
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_by_topic_text
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["civic", "alpr"],
                       target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["tech"],
                       target_stage="search"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["civic"],
                       target_stage="hop_planner"),
    ])
    # "civic" appears in topic text -> matches a (tagged civic/alpr) and c (tagged civic).
    # b (tagged only "tech") does NOT match — "tech" not in topic text.
    relevant = filter_by_topic_text(f, topics=["civic ALPR programs in Greenville"])
    assert {p.id for p in relevant} == {"a", "c"}


def test_filter_by_topic_text_case_insensitive():
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_by_topic_text
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["Civic"],
                       target_stage="search"),
    ])
    relevant = filter_by_topic_text(f, topics=["alpr in CIVIC contexts"])
    assert len(relevant) == 1


def test_filter_by_domain_overlap():
    """filter_relevant matches by exact domain_tags overlap. Used at Stage 10d
    when the case has its derived domain_tags available."""
    from learned_patterns import LearnedPatternsFile, LearnedPattern, filter_relevant
    f = LearnedPatternsFile(patterns=[
        LearnedPattern(id="a", name="A", body="", domain_tags=["civic", "alpr"],
                       target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["tech"],
                       target_stage="search"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["civic"],
                       target_stage="hop_planner"),
    ])
    relevant = filter_relevant(f, run_domain_tags=["civic"])
    assert {p.id for p in relevant} == {"a", "c"}


def test_group_by_target_stage():
    """group_by_stage returns dict[stage -> list[LearnedPattern]]."""
    from learned_patterns import LearnedPattern, group_by_stage
    patterns = [
        LearnedPattern(id="a", name="A", body="", domain_tags=["x"], target_stage="search"),
        LearnedPattern(id="b", name="B", body="", domain_tags=["x"], target_stage="hop_planner"),
        LearnedPattern(id="c", name="C", body="", domain_tags=["x"], target_stage="search"),
    ]
    grouped = group_by_stage(patterns)
    assert {p.id for p in grouped["search"]} == {"a", "c"}
    assert {p.id for p in grouped["hop_planner"]} == {"b"}
    assert grouped.get("classify", []) == []

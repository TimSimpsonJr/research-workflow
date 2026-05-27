"""Heuristic candidate detection over case records.

Pure Python; no LLM calls. Produces candidate observations for the accumulator.

See docs/plans/2026-05-27-v3-1-case-learning-design.md Section 6.1.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any


def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:4]


def _make_pattern_id(domain_slug: str, category: str, stable_key: str) -> str:
    """Deterministic pattern_id. `stable_key` MUST be the same string for the
    same underlying observation across runs (e.g., the dominant tier name,
    the winning hop pattern name, the templatized query). Do NOT pass
    timestamps or other per-run values — those break sessions_seen accumulation.
    """
    safe_domain = domain_slug.replace("/", "-").replace(" ", "-").lower()
    safe_cat = category.replace("_", "-").lower()
    return f"{safe_domain}-{safe_cat}-{_short_hash(stable_key)}"


def detect_source_tier_dominance(
    cases: list[dict],
    *,
    min_dominance: float = 0.5,
    min_cases: int = 3,
) -> list[dict]:
    """Detect domains where one source tier (T1 / T2 / T3 / T4) consistently
    dominates patterns_that_worked.source_tiers across cases.

    Returns a list of candidate dicts ready for accumulator.record_observation().
    """
    by_domain: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        key = tuple(sorted(case.get("domain_tags", [])))
        if not key:
            continue
        by_domain[key].append(case)

    candidates = []

    for domain_tags, domain_cases in by_domain.items():
        if len(domain_cases) < min_cases:
            continue
        # Aggregate source tier distribution across cases
        tier_totals = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
        for c in domain_cases:
            tiers = (c.get("patterns_that_worked", {}) or {}).get("source_tiers", {}) or {}
            for k, v in tiers.items():
                if k in tier_totals:
                    tier_totals[k] += v
        total = sum(tier_totals.values())
        if total == 0:
            continue
        dominant_tier = max(tier_totals, key=lambda k: tier_totals[k])
        share = tier_totals[dominant_tier] / total
        if share < min_dominance:
            continue

        domain_slug = "-".join(domain_tags)
        name = f"{dominant_tier} sources dominate for {' / '.join(domain_tags)} queries"
        body = (
            f"{dominant_tier} sources tend to score highest for queries in this domain. "
            f"Observed share: {share:.0%} across {len(domain_cases)} cases."
        )
        evidence = [
            {
                "case_id": c.get("case_id"),
                "signal": f"{dominant_tier}={(c.get('patterns_that_worked', {}) or {}).get('source_tiers', {}).get(dominant_tier, 0)}, "
                          f"conf_avg={_avg_confidence(c):.2f}",
            }
            for c in domain_cases
        ]
        # stable_key is the dominant tier name — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "source-tier-bias", dominant_tier)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "source-tier-bias",
            "target_stage": "search",
            "domain_tags": list(domain_tags),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates


def _avg_confidence(case: dict) -> float:
    cpt = case.get("confidence_per_topic", {})
    if not cpt:
        return 0.0
    vals = [v for v in cpt.values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def detect_hop_pattern_lift(
    cases: list[dict],
    *,
    min_dominance: float = 0.1,
    min_cases: int = 3,
) -> list[dict]:
    """Detect domains where one hop pattern (entity_expansion / temporal_progression
    / conceptual_deepening / causal_chain) dominates the patterns_that_worked.hop_chain
    counts across cases.

    Note: ``patterns_that_worked.hop_chain`` is the set of hop patterns that lifted
    confidence enough to land a topic in patterns_that_worked at run time — so
    frequency-dominance there IS a lift signal. ``min_dominance=0.1`` means the
    winning pattern must hold >= 90% share of all hop-chain entries (i.e., the
    second-best pattern's share is <= 10%).

    A future enhancement could replace this proxy with a true confidence-delta
    computation if the case-record schema starts emitting per-hop confidence
    history (currently it emits per-topic only).
    """
    by_domain: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        key = tuple(sorted(case.get("domain_tags", [])))
        if not key:
            continue
        by_domain[key].append(case)

    candidates = []

    for domain_tags, domain_cases in by_domain.items():
        if len(domain_cases) < min_cases:
            continue
        # Count hop pattern occurrences in patterns_that_worked
        pattern_counts: dict[str, int] = defaultdict(int)
        for c in domain_cases:
            chain = (c.get("patterns_that_worked", {}) or {}).get("hop_chain", []) or []
            for p in chain:
                pattern_counts[p] += 1
        if not pattern_counts:
            continue
        # Pick the most frequent
        winning_pattern = max(pattern_counts, key=lambda k: pattern_counts[k])
        share = pattern_counts[winning_pattern] / sum(pattern_counts.values())
        if share < (1 - min_dominance):  # winner needs strong dominance
            continue

        domain_slug = "-".join(domain_tags)
        name = f"{winning_pattern} preferred for {' / '.join(domain_tags)} topics"
        body = (
            f"The {winning_pattern} hop pattern appears in patterns_that_worked "
            f"across {pattern_counts[winning_pattern]}/{sum(pattern_counts.values())} "
            f"hop transitions in this domain."
        )
        evidence = [
            {
                "case_id": c.get("case_id"),
                "signal": f"hop_chain={(c.get('patterns_that_worked', {}) or {}).get('hop_chain', [])}, "
                          f"conf_avg={_avg_confidence(c):.2f}",
            }
            for c in domain_cases
        ]
        # stable_key is the winning hop-pattern name — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "hop-pattern-bias", winning_pattern)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "hop-pattern-bias",
            "target_stage": "hop_planner",
            "domain_tags": list(domain_tags),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates


_YEAR_PATTERN = re.compile(r"\b(19|20|21)\d{2}\b")
_PROPER_NOUN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


def _templatize(query: str) -> str:
    """Replace likely proper-noun spans and years with placeholders."""
    t = _YEAR_PATTERN.sub("[year]", query)
    t = _PROPER_NOUN.sub("[entity]", t)
    return t.strip().lower()


def detect_query_template_recurrence(
    cases: list[dict],
    *,
    min_recurrence: int = 3,
) -> list[dict]:
    """Detect query templates that recur across cases as queries that worked."""
    by_domain_template: dict[tuple, list[dict]] = defaultdict(list)
    for case in cases:
        domain = tuple(sorted(case.get("domain_tags", [])))
        if not domain:
            continue
        queries = (case.get("patterns_that_worked", {}) or {}).get("queries", []) or []
        for q in queries:
            if not isinstance(q, str):
                continue
            template = _templatize(q)
            by_domain_template[(domain, template)].append(
                {"case_id": case.get("case_id"), "raw_query": q}
            )

    candidates = []
    for (domain, template), instances in by_domain_template.items():
        if len(instances) < min_recurrence:
            continue
        domain_slug = "-".join(domain)
        name = f"Recurring query template for {' / '.join(domain)}: {template}"
        body = (
            f"Query template `{template}` recurred {len(instances)} times across "
            f"recent runs in this domain."
        )
        evidence = [
            {"case_id": inst["case_id"], "signal": f"raw_query={inst['raw_query']!r}"}
            for inst in instances
        ]
        # stable_key is the templatized query — recurs identically across runs
        pid = _make_pattern_id(domain_slug, "query-template", template)
        candidates.append({
            "pattern_id": pid,
            "name": name,
            "category": "query-template",
            "target_stage": "search",
            "domain_tags": list(domain),
            "proposed_promotion_body": body,
            "evidence_rows": evidence,
        })
    return candidates

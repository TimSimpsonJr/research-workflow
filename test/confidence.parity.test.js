// Parity guard: lib/confidence.js (JS, used by the batch workflow) must produce
// the SAME values as scripts/confidence.py (Python, used by the inline skill).
//
// The two implementations are kept in sync by SHARED TEST VECTORS: every vector
// + expected value below mirrors an assertion in tests/test_confidence.py. If
// confidence.py drifts, its pytest fails; if confidence.js drifts, this fails.
// Both are pinned to the same numbers, so they cannot silently diverge.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  tierDiversityWeight, topicCoverage, primarySourcePresence,
  sourceCountAdequacy, computeConfidence, contradictionRate, tierFromScore,
} from '../lib/confidence.js';

const EPS = 1e-9;
const approx = (actual, expected) =>
  assert.ok(Math.abs(actual - expected) < EPS, `expected ${actual} ≈ ${expected}`);

test('parity: tier_diversity_weight (test_confidence.py)', () => {
  approx(tierDiversityWeight([{ tier: 'T1' }, { tier: 'T1' }, { tier: 'T1' }]), 1.0);
  approx(tierDiversityWeight([{ tier: 'T4' }, { tier: 'T4' }, { tier: 'T4' }]), 0.25);
  approx(tierDiversityWeight([{ tier: 'T1' }, { tier: 'T2' }, { tier: 'T3' }, { tier: 'T4' }]), (1.0 + 0.75 + 0.5 + 0.25) / 4);
  approx(tierDiversityWeight([]), 0.0);
  approx(tierDiversityWeight([{ tier: 'T1' }, { url: 'no-tier-key' }]), (1.0 + 0.25) / 2); // missing → T4
  approx(tierDiversityWeight([{ tier: 'T1' }, { tier: 'T9' }]), (1.0 + 0.25) / 2);          // bogus → T4
});

test('parity: topic_coverage (test_confidence.py)', () => {
  approx(topicCoverage([{ tier: 'T2' }, { tier: 'T2' }, { tier: 'T2' }]), 1.0);
  approx(topicCoverage([{ tier: 'T1' }, { tier: 'T1' }]), 2 / 3);
  approx(topicCoverage([{ tier: 'T3' }, { tier: 'T4' }, { tier: 'T3' }]), 0.0);
  approx(topicCoverage([{ tier: 'T1' }, { url: 'no-tier' }, { tier: 'T2' }]), 2 / 3);
  approx(topicCoverage([{ tier: 'T1' }, { tier: 'T3' }, { tier: 'T2' }, { tier: 'T4' }]), 2 / 3);
});

test('parity: primary_source_presence (test_confidence.py)', () => {
  approx(primarySourcePresence([{ is_primary: false }, { is_primary: false }]), 0.0);
  approx(primarySourcePresence([{ is_primary: true }, { is_primary: false }]), 0.5);
  approx(primarySourcePresence([{ is_primary: true }, { is_primary: true }]), 1.0);
  approx(primarySourcePresence(Array(5).fill({ is_primary: true })), 1.0);
});

test('parity: source_count_adequacy (test_confidence.py)', () => {
  approx(sourceCountAdequacy(10, 20), 0.5);
  approx(sourceCountAdequacy(20, 20), 1.0);
  approx(sourceCountAdequacy(30, 20), 1.0);
  approx(sourceCountAdequacy(0, 20), 0.0);
});

test('parity: compute_confidence strong/weak/empty (test_confidence.py)', () => {
  const strong = computeConfidence([
    { tier: 'T1', is_primary: true },
    { tier: 'T1', is_primary: false },
    { tier: 'T2', is_primary: true },
    { tier: 'T2', is_primary: false },
  ], 'standard');
  // 0.4*0.875 + 0.3*1.0 + 0.2*1.0 + 0.1*(4/20) = 0.87
  assert.ok(strong >= 0.86 && strong <= 0.88, `strong=${strong}`);

  const weak = computeConfidence([{ tier: 'T4', is_primary: false }], 'standard');
  // 0.4*0.25 + 0 + 0 + 0.1*(1/20) = 0.105
  assert.ok(weak >= 0.10 && weak <= 0.11, `weak=${weak}`);

  approx(computeConfidence([], 'standard'), 0.0);
});

test('parity: contradiction_rate (test_confidence.py)', () => {
  approx(contradictionRate([{ url: 'a' }, { url: 'b' }, { url: 'c' }], []), 0.0);
  approx(contradictionRate([{ url: 'a' }, { url: 'b' }, { url: 'c' }], [{ source_a: 'a', source_b: 'b' }]), 1.0); // 1/(3*0.3)>1 → cap
  const prop = contradictionRate(Array.from({ length: 10 }, (_, i) => ({ url: `s${i}` })), [{}]);
  assert.ok(prop >= 0.33 && prop <= 0.34, `prop=${prop}`); // 1/(10*0.3) ≈ 0.333
  approx(contradictionRate([{ url: 'a' }], []), 0.0); // <2 sources
});

test('parity: tier_from_score buckets (test_confidence.py)', () => {
  for (const [score, tier] of [[0.95, 'T1'], [0.9, 'T1'], [0.85, 'T2'], [0.7, 'T2'], [0.6, 'T3'], [0.5, 'T3'], [0.4, 'T4'], [0.3, 'T4'], [0.1, 'T4']]) {
    assert.equal(tierFromScore(score), tier);
  }
});

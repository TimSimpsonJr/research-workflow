// Research quality scoring — JS twin of scripts/confidence.py.
//
// Pure functions for confidence + contradiction signals from a topic's sources,
// plus the hop-planner continue/stop/replan decision. No I/O, no imports.
// Kept value-for-value in sync with confidence.py via shared test vectors
// (test/confidence.parity.test.js). The research-batch workflow inlines a copy
// of these definitions (exports stripped); test/contract.test.js guards that
// the inlined copy matches this source.

export const DEPTH_PROFILES = {
  quick:      { max_hops: 1, target_sources: 10, confidence_target: 0.6 },
  standard:   { max_hops: 3, target_sources: 20, confidence_target: 0.7 },
  deep:       { max_hops: 4, target_sources: 40, confidence_target: 0.8 },
  exhaustive: { max_hops: 5, target_sources: 50, confidence_target: 0.9 },
};
const TIER_WEIGHTS = { T1: 1.0, T2: 0.75, T3: 0.5, T4: 0.25 };

export function getDepthProfile(name) {
  const p = DEPTH_PROFILES[name];
  if (!p) throw new Error(`unknown depth: ${name}`);
  return p;
}
export function tierDiversityWeight(sources) {
  if (!sources.length) return 0;
  return sources.reduce((a, s) => a + (TIER_WEIGHTS[s.tier] ?? 0.25), 0) / sources.length;
}
export function topicCoverage(sources) {
  const t2plus = sources.filter((s) => s.tier === 'T1' || s.tier === 'T2').length;
  return Math.min(1, t2plus / 3);
}
export function primarySourcePresence(sources) {
  return Math.min(1, sources.filter((s) => s.is_primary).length / 2);
}
export function sourceCountAdequacy(count, target) {
  if (target <= 0) return 0;
  return Math.min(1, count / target);
}
export function computeConfidence(sources, depth) {
  if (!sources.length) return 0;
  const target = getDepthProfile(depth).target_sources;
  return (
    0.4 * tierDiversityWeight(sources) +
    0.3 * topicCoverage(sources) +
    0.2 * primarySourcePresence(sources) +
    0.1 * sourceCountAdequacy(sources.length, target)
  );
}
export function contradictionRate(sources, contradictions) {
  if (sources.length < 2 || !contradictions.length) return 0;
  return Math.min(1, contradictions.length / (sources.length * 0.3));
}
export function tierFromScore(score) {
  if (score >= 0.9) return 'T1';
  if (score >= 0.7) return 'T2';
  if (score >= 0.5) return 'T3';
  return 'T4';
}
// Hop-planner Step 3 rules, order-sensitive. confidence.py / SKILL Stage 5 parity.
export function decide({ confidence, contradictionRate: cr, hop, maxHops, target }) {
  if (confidence >= target && cr <= 0.3) return 'stop';
  if (hop >= maxHops) return 'stop';
  if (confidence < target * 0.7 && hop === 1) return 'replan';
  return 'continue';
}

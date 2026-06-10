import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEPTH_PROFILES, getDepthProfile, tierDiversityWeight, topicCoverage,
  primarySourcePresence, sourceCountAdequacy, computeConfidence,
  contradictionRate, tierFromScore, decide,
} from '../lib/confidence.js';

test('depth profiles', () => {
  assert.equal(getDepthProfile('standard').confidence_target, 0.7);
  assert.equal(getDepthProfile('exhaustive').max_hops, 5);
  assert.throws(() => getDepthProfile('nope'));
});

test('tier diversity: empty → 0, unknown tier → 0.25', () => {
  assert.equal(tierDiversityWeight([]), 0);
  assert.equal(tierDiversityWeight([{ tier: 'T1' }, { tier: 'T3' }]), 0.75);
  assert.equal(tierDiversityWeight([{}]), 0.25); // missing tier treated as T4
});

test('topic coverage caps at 1.0 (3 T2+)', () => {
  assert.equal(topicCoverage([{ tier: 'T1' }, { tier: 'T2' }, { tier: 'T2' }, { tier: 'T1' }]), 1);
  assert.equal(topicCoverage([{ tier: 'T3' }]), 0);
});

test('primary presence caps at 1.0 (2 primary)', () => {
  assert.equal(primarySourcePresence([{ is_primary: true }, { is_primary: true }]), 1);
  assert.equal(primarySourcePresence([{ is_primary: true }]), 0.5);
});

test('source count adequacy', () => {
  assert.equal(sourceCountAdequacy(10, 20), 0.5);
  assert.equal(sourceCountAdequacy(30, 20), 1);
  assert.equal(sourceCountAdequacy(5, 0), 0);
});

test('compute confidence: empty → 0', () => {
  assert.equal(computeConfidence([], 'standard'), 0);
});

test('contradiction rate', () => {
  assert.equal(contradictionRate([{}], []), 0);            // <2 sources
  assert.equal(contradictionRate([{}, {}, {}], []), 0);     // no contradictions
  assert.equal(contradictionRate([{}, {}, {}, {}], [{}, {}]), Math.min(1, 2 / (4 * 0.3)));
});

test('tier from score', () => {
  assert.equal(tierFromScore(0.95), 'T1');
  assert.equal(tierFromScore(0.7), 'T2');
  assert.equal(tierFromScore(0.5), 'T3');
  assert.equal(tierFromScore(0.1), 'T4');
});

test('decide: stop on target, stop on maxhops, replan, continue', () => {
  assert.equal(decide({ confidence: 0.8, contradictionRate: 0.1, hop: 1, maxHops: 3, target: 0.7 }), 'stop');
  assert.equal(decide({ confidence: 0.4, contradictionRate: 0.1, hop: 3, maxHops: 3, target: 0.7 }), 'stop');
  assert.equal(decide({ confidence: 0.3, contradictionRate: 0.1, hop: 1, maxHops: 3, target: 0.7 }), 'replan');
  assert.equal(decide({ confidence: 0.6, contradictionRate: 0.1, hop: 2, maxHops: 3, target: 0.7 }), 'continue');
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as schemas from '../lib/schemas.js';

const EXPECTED = {
  SEARCH: ['selected_urls'],
  SUMMARIES: ['items'],
  HOP_NEXT: ['decision', 'self_reflection'],
  CLASSIFY: ['notes_to_create'],
  WIKILINK_RESULT: ['edits', 'stats'],
  MOC_RESULT: ['updated'],
  WRITE_RESULT: ['written_notes'],
  THREADS: ['threads', 'batch_stats'],
};

test('every expected schema is exported and well-formed', () => {
  for (const [name, required] of Object.entries(EXPECTED)) {
    const s = schemas[name];
    assert.ok(s, `missing schema export: ${name}`);
    assert.equal(s.type, 'object', `${name}.type must be 'object'`);
    assert.deepEqual(s.required, required, `${name}.required mismatch`);
    assert.ok(s.properties && typeof s.properties === 'object', `${name}.properties must be an object`);
    // Every required key must have a declared property.
    for (const key of required) {
      assert.ok(key in s.properties, `${name}.properties missing required key '${key}'`);
    }
  }
});

test('no unexpected schema exports leaked in', () => {
  const exported = Object.keys(schemas).sort();
  assert.deepEqual(exported, Object.keys(EXPECTED).sort());
});

test('HOP_NEXT.next_hop is nullable (researcher hop-planner emits null on stop)', () => {
  const t = schemas.HOP_NEXT.properties.next_hop.type;
  assert.ok(Array.isArray(t) && t.includes('null'), 'next_hop must allow null');
});

test('nested item schemas pin load-bearing keys', () => {
  assert.deepEqual(schemas.SEARCH.properties.selected_urls.items.required, ['url', 'tier', 'is_primary', 'credibility_score']);
  assert.deepEqual(schemas.SUMMARIES.properties.items.items.required, ['url', 'summary', 'tier', 'is_primary']);
  assert.deepEqual(schemas.CLASSIFY.properties.notes_to_create.items.required, ['title', 'content', 'priority', 'action']);
  assert.deepEqual(schemas.WIKILINK_RESULT.properties.edits.items.required, ['file', 'find', 'replace']);
});

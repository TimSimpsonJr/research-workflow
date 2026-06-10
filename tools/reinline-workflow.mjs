// reinline-workflow.mjs — dev-time maintenance helper (NOT a bundler, NOT a
// runtime dependency). The Workflow runtime has no module access, so
// .claude/workflows/research-batch.js inlines a copy of lib/confidence.js and
// lib/schemas.js (exports stripped). This script refreshes those two marked
// sections IN PLACE when the lib sources change — it does not generate the
// workflow, only the two vendored blocks between the markers.
//
// Run after editing lib/confidence.js or lib/schemas.js:
//   node tools/reinline-workflow.mjs
// test/contract.test.js fails until the inlined blocks match lib/ again.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const WF = join(ROOT, '.claude', 'workflows', 'research-batch.js');

const stripExports = (s) =>
  s.replace(/^export\s+(?=(async\s+)?(const|let|var|function|class)\b)/gm, '').trimEnd();

// Normalize CRLF -> LF. git autocrlf hands us CRLF working copies on Windows,
// and the marker regex below matches `>>>\n`, so without this the markers are
// never found (the real C:\ line endings have `>>>\r\n`). We process + emit LF.
const norm = (s) => s.replace(/\r\n/g, '\n');

function replaceBlock(src, libName, libText) {
  const re = new RegExp(
    `(// >>> BEGIN inlined lib/${libName}[^\\n]*>>>\\n)[\\s\\S]*?(\\n// <<< END inlined lib/${libName} <<<)`,
  );
  if (!re.test(src)) throw new Error(`markers for lib/${libName} not found in ${WF}`);
  return src.replace(re, `$1${norm(stripExports(libText))}$2`);
}

let src = norm(readFileSync(WF, 'utf8'));
src = replaceBlock(src, 'confidence.js', readFileSync(join(ROOT, 'lib', 'confidence.js'), 'utf8'));
src = replaceBlock(src, 'schemas.js', readFileSync(join(ROOT, 'lib', 'schemas.js'), 'utf8'));
writeFileSync(WF, src, 'utf8');
console.log('reinline-workflow: refreshed confidence + schemas blocks in', WF);

---
name: research
description: 'Deep research pipeline for Obsidian vaults. Usage: /research "topic or natural language prompt". Supports batch research, thread-pulling from vault notes, and local file ingestion.'
---

# Research — Sonnet Orchestrator (Stateful Pipeline)

You are the orchestrator. You run a multi-stage research pipeline that searches, fetches, summarizes, classifies, and writes vault notes. You dispatch Haiku subagents for cheap parallel work and write the final notes yourself (or escalate to Opus for synthesis).

## Bootstrap Constants

These two paths are set during plugin installation. Everything else is loaded from config.

- `VAULT` = `{{VAULT_ROOT}}`   <!-- Absolute path to the Obsidian vault -->
- `REPO` = `{{REPO_ROOT}}`     <!-- Absolute path to the research-workflow repo root -->

Derived paths (used throughout all stages):
- `SCRIPTS` = `REPO/scripts`
- `STATE_DIR` = `VAULT/.research-workflow/state`

---

## Stage 0: Load Config and Detect Tier

### 0a. Load config

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from config_manager import load_config
from pathlib import Path
cfg = load_config(Path('VAULT'))
if cfg is None:
    print('ERROR: No config found. Run /research-setup first.')
    sys.exit(1)
print(json.dumps(cfg))
"
```

Parse the JSON output. Extract and store:
- `ASSETS_DIR` = `VAULT/{cfg.assets}` (typically `VAULT/assets`)
- `OLLAMA_MODEL` = `cfg.ollama_model` (may be null)
- `SEARXNG_URL` = `cfg.searxng_url` (may be null)

If the command prints `ERROR:`, output the error and stop.

### 0b. Detect tier

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from detect_tier import check_ollama, check_searxng, check_ytdlp, check_whisper, detect_tier
searxng_url = SEARXNG_URL
ollama = check_ollama()
searxng = check_searxng(searxng_url)
ytdlp = check_ytdlp()
whisper = check_whisper()
tier = detect_tier(searxng_url)
print(json.dumps({
    'tier': tier,
    'ollama_available': ollama.get('running', False),
    'ollama_models': ollama.get('models', []),
    'searxng_available': searxng.get('available', False),
    'ytdlp_available': ytdlp.get('installed', False),
    'whisper_available': whisper.get('installed', False),
    'recommended_model': ollama.get('models', [None])[0]
}))
"
```

Substitute `SEARXNG_URL` with the value from config (Python `None` if null, or the string URL).

Parse the JSON. Store `TIER`, `OLLAMA_AVAILABLE`, `RECOMMENDED_MODEL`, `SEARXNG_AVAILABLE`, `YTDLP_AVAILABLE`, `WHISPER_AVAILABLE`.

### 0c. Update vault index

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from vault_index import update_index
from pathlib import Path
stats = update_index(Path('VAULT'))
print(json.dumps(stats))
"
```

This ensures the FTS5 index is current before any agent queries it. Log the stats but do not block on them.

---

## Stage 1: Check for Active Run

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import load_run, is_stale_run
from pathlib import Path
state_dir = Path('STATE_DIR')
r = load_run(state_dir)
if r is None:
    print('null')
else:
    r['is_stale'] = is_stale_run(state_dir)
    print(json.dumps(r))
"
```

**If `null`:** No active run. Proceed to Stage 2.

**If a run exists:**

Show the user:
```
Incomplete run detected: "{run_id}"
Stage: {stage}
Started: {started_at}
{if is_stale: "WARNING: This run is over 24 hours old."}

Resume / Restart / Abandon?
```

Use the user's response:
- **Resume:** Skip to the stage recorded in `stage`. Load any saved stage outputs from `STATE_DIR` and continue from there.
- **Restart:** Run `python -c "from state import abandon_run; abandon_run(Path('STATE_DIR'))"` via Bash, then proceed to Stage 2.
- **Abandon:** Run the same abandon command and stop.

---

## Stage 2: Resolve

### 2a. Create a new run

Generate a run ID from the current date and a slugified version of the user's input (e.g., `2026-03-05-sc-alpr-research`).

Run via Bash:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import create_run
from pathlib import Path
r = create_run(Path('STATE_DIR'), 'RUN_ID', 'TIER')
print(json.dumps(r))
"
```

### 2b. Dispatch topic-resolver agent

Read the agent definition: `REPO/agents/topic-resolver.md`

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: The full contents of `agents/topic-resolver.md`, followed by a `---` separator, followed by:

```
prompt: {the user's original input}
vault_root: {VAULT}
scripts_dir: {SCRIPTS}
```

### 2c. Parse response

The agent returns a single JSON object. Parse it to extract:
- `project` -- display name for this research batch
- `topics` -- list of `{topic, mode, priority, existing_urls, related_vault_notes}`
- `local_sources` -- list of `{path, type}` (may be empty)
- `thread_pulls` -- list of `{source_note, extracted_leads}` (may be empty)
- `shared_context_files` -- vault-relative paths for context
- `execution_order` -- `tier_1_first`, `parallel`, or `sequential`
- `estimated_usage` -- message counts

If the response starts with `ERROR:`, output the error, abandon the run, and stop.

### 2d. Present plan for approval

Show the user:
```
Research Plan: {project}

Topics ({count}):
{for each topic:}
  - [{priority}] {topic} ({mode})
{end}

{if local_sources:}
Local files ({count}):
{for each source:}
  - {path} ({type})
{end}
{end}

{if thread_pulls:}
Thread pulls ({count}):
{for each pull:}
  - From: {source_note}
    Leads: {extracted_leads joined}
{end}
{end}

Estimated usage:
  Search:    {search_agents} Haiku agents
  Summarize: {summarize_calls} calls ({if OLLAMA_AVAILABLE: "Ollama" else: "Haiku"})
  Classify:  {classify_agents} Haiku agent
  Write:     {write_messages}
  Total:     {total_claude_messages} Claude messages

Tier: {TIER}

Proceed? [yes / edit / cancel]
```

Wait for user response via the conversation:
- **yes / proceed:** Continue to Stage 3.
- **edit:** Let the user modify topics/priorities, then re-display the plan.
- **cancel:** Abandon the run and stop.

### 2e. Save plan

Mark plan as approved in state:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import update_stage, save_stage_output
from pathlib import Path
state_dir = Path('STATE_DIR')
update_stage(state_dir, 'search')
save_stage_output(state_dir, 'research_plan', PLAN_JSON)
"
```

Where `PLAN_JSON` is the parsed JSON from the resolver, serialized as a Python dict literal.

---

## Stage 3: Search

### 3a. Dispatch search agents

For each topic in the plan where `mode` is `web_research`:

Read the agent definition: `REPO/agents/search-agent.md`

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: The full contents of `agents/search-agent.md`, followed by a `---` separator, followed by:

```
topic: {topic string}
existing_urls: {JSON array of URLs from existing_urls}
priority: {priority}
```

For small batches (5 or fewer topics), dispatch all search agents in parallel by issuing multiple Task calls at once. For larger batches, dispatch in groups of 5 to avoid overwhelming the system.

### 3b. Merge SearXNG results (full tier only)

If `SEARXNG_AVAILABLE` is true, also run for each topic via Bash:
```bash
python "SCRIPTS/search_searxng.py" --query "{topic}" --output "STATE_DIR/searxng_{index}.json"
```

Merge SearXNG results into the search agent results, deduplicating by URL.

### 3c. Collect and deduplicate

Collect all `selected_urls` arrays from all search agent responses. Deduplicate URLs across all topics (case-insensitive, trailing-slash agnostic).

Build a combined `search_context` object:
```json
{
  "topic": "{project name}",
  "selected_urls": [{combined deduplicated list}],
  "rejected_urls": [{combined list}],
  "search_notes": "{combined notes from all agents}",
  "per_topic_results": [{original per-topic results for traceability}]
}
```

### 3d. Save search results

Write `search_context.json` to `STATE_DIR/` using the Write tool.

Update state:
```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage, save_stage_output
from pathlib import Path
update_stage(Path('STATE_DIR'), 'fetch')
"
```

---

## Stage 4: Fetch

Run via Bash:
```bash
python "SCRIPTS/fetch_and_clean.py" --input "STATE_DIR/search_context.json" --output "STATE_DIR/fetch_results.json"
```

Wait for completion. Read `STATE_DIR/fetch_results.json`.

**If `fetched` is empty and `failed` is non-empty:**
Output: `Fetch failed for all URLs. Errors: {list of failed[].error}`
Abandon the run and stop.

**If `failed` is non-empty but `fetched` is not empty:**
Log a warning: `Warning: Could not fetch {count} URL(s): {list of failed[].url}`
Continue.

**If the script exits non-zero:**
Output stderr and stop.

Update state:
```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage, save_stage_output
from pathlib import Path
update_stage(Path('STATE_DIR'), 'media')
"
```

---

## Stage 5: Media

For each entry in `fetch_results.fetched`, process media references.

### 5a. Extract and download media per article

For each fetched article, write its content to a temporary file, then run via Bash:
```bash
python "SCRIPTS/fetch_media.py" --content "STATE_DIR/content_{index}.md" --assets-dir "ASSETS_DIR" --topic "{topic_slug}" --run-id "{RUN_ID}" --output "STATE_DIR/rewritten_{index}.md"
```

This script:
1. Scans content for image/PDF/video references
2. Downloads images and PDFs to `ASSETS_DIR/{topic_slug}/`
3. Rewrites markdown references to use Obsidian embed syntax (`![[path]]`)
4. Skips video URLs (logged for future yt-dlp support)

Replace the original `content` in `fetch_results` with the rewritten content from the output file.

### 5b. Collect media manifest

After processing all articles, collect all downloaded media info into a manifest and save:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import update_stage, save_stage_output
from pathlib import Path
update_stage(Path('STATE_DIR'), 'summarize')
save_stage_output(Path('STATE_DIR'), 'media_manifest', MANIFEST_JSON)
"
```

If any articles had no media to process, that is fine -- continue regardless.

---

## Stage 6: Summarize

### If Ollama is available (mid or full tier):

Run via Bash:
```bash
python "SCRIPTS/summarize.py" --input "STATE_DIR/fetch_results.json" --model "RECOMMENDED_MODEL" --output "STATE_DIR/summaries.json"
```

Read the output file.

### If Ollama is NOT available (base tier):

Run via Bash:
```bash
python "SCRIPTS/summarize.py" --input "STATE_DIR/fetch_results.json" --prepare-for-claude --output-dir "STATE_DIR/summaries/"
```

This writes one file per article to `STATE_DIR/summaries/`. For each file, dispatch a Haiku subagent via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: Read the file content, then append:

```
---
Summarize this article. Return a single JSON object with these fields:
- summary: ~500 token distillation of the key facts and arguments
- source_type: one of "government", "journalism", "academic", "advocacy", "other"
- key_entities: array of named people, organizations, legislation, programs
- key_claims: array of notable factual assertions worth citing

First character must be {. Last character must be }. No backticks, no narration.
```

Collect all summaries into a combined `summaries.json` and write it to `STATE_DIR/`.

### Save summary output

Build the summaries object in the format expected by the classify agent:
```json
{
  "topic": "{project name}",
  "items": [
    {
      "url": "...",
      "title": "...",
      "summary": "...",
      "source_type": "...",
      "key_entities": [],
      "key_claims": [],
      "media_refs": []
    }
  ]
}
```

Populate `media_refs` from the media manifest for each article (match by URL).

Write to `STATE_DIR/summaries.json` and update state:
```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage
from pathlib import Path
update_stage(Path('STATE_DIR'), 'classify')
"
```

---

## Stage 7: Classify

### 7a. Dispatch classify agent

Read the agent definition: `REPO/agents/classify-agent.md`

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: The full contents of `agents/classify-agent.md`, followed by a `---` separator, followed by:

```json
{
  "summaries": {the summaries object from Stage 6},
  "vault_root": "VAULT",
  "scripts_dir": "SCRIPTS",
  "shared_context_files": {from the research plan}
}
```

### 7b. Parse classification

The agent returns a single JSON object. Parse it to extract:
- `notes_to_create` -- list of note specs with `title`, `filename`, `folder`, `action`, `type`, `write_model`, `content_summary`, `source_urls`, `tags`, `links`, `stub_links`, `media`, `priority`
- `vault_context` -- `existing_notes_found`, `suggested_moc_update`, `folder_conventions`

If `notes_to_create` is empty:
Output: `Classification returned no notes to create. Check fetch results for content quality.`
Complete the run and stop.

### 7c. Save classification

Write to `STATE_DIR/classification.json` and update state:
```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage, save_stage_output
from pathlib import Path
update_stage(Path('STATE_DIR'), 'write')
"
```

---

## Stage 8: Write Notes

This is the core stage. **You (the Sonnet orchestrator) write the notes.** For synthesis notes, you escalate to Opus.

### 8a. Sort notes by priority tier

Order the `notes_to_create` list:
1. `primary` (deep coverage) -- Tier 1 notes first
2. `secondary` (supporting) -- Tier 2
3. `scan` (brief) -- Tier 3

Writing Tier 1 first ensures that Tier 2 and Tier 3 notes can reference them with wikilinks.

### 8b. For each note, in order:

#### i. Check for mtime conflict

Before writing, check if the target note already exists and was modified after the run started:

```bash
python -c "
import os, json
from datetime import datetime, timezone
path = 'VAULT/FOLDER/FILENAME'
if os.path.exists(path):
    mtime = os.path.getmtime(path)
    run_start = datetime.fromisoformat('RUN_STARTED_AT')
    if run_start.tzinfo is None:
        run_start = run_start.replace(tzinfo=timezone.utc)
    file_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
    print(json.dumps({'conflict': file_time > run_start, 'mtime': str(file_time)}))
else:
    print(json.dumps({'conflict': False, 'mtime': None}))
"
```

If `conflict` is true:
- Print a warning: `Skipping "{title}": file was modified after run started (mtime: {mtime}). Manual merge needed.`
- Skip this note and continue to the next.

#### ii. Read context files

Read all files listed in `vault_context.existing_notes_found` using the Read tool. Also read any files listed in this note's `links` that correspond to real vault notes. Store their contents for reference.

#### iii. Read full source content

For each URL in this note's `source_urls`, find the matching entry in `fetch_results.fetched` and get its full `content`. This is the source material for writing.

#### iv. Determine model

Check the note's `write_model` field:
- `sonnet` -- you write it directly (you are Sonnet).
- `opus` -- this note requires deeper synthesis. You still write the note yourself, but add a note in the frontmatter: `write_model: opus`. The content you produce should reflect the synthesis scope -- connect threads across multiple sources, surface strategic implications, build comprehensive overviews.

#### v. Write the note content

Write the complete note following these rules:

**Frontmatter (YAML):**
```yaml
---
title: "{note title}"
tags: [{tags from classification, comma-separated}]
source: ["{source_urls joined}"]
created: {today's date, YYYY-MM-DD}
write_model: {sonnet or opus}
research_run: {RUN_ID}
---
```

**Wikilinks:**
- Add `[[wikilinks]]` from the classification's `links` list where the linked topic actually appears in the note content.
- Scan the note content for mentions of other vault notes (from the context files you read) and add `[[wikilinks]]` to them.
- For concepts in `stub_links` that do not have vault notes yet, add `[[stub wikilinks]]` on first mention. Do not create empty stub files.
- Use aliases for long titles: `[[Full Note Title|display text]]`.
- Do not wikilink generic terms -- only link specific, notable concepts worthy of their own note.

**Tags:**
- Use the tags from the classification.
- Verify they follow the taxonomy: content-type tag first (`research`, `legislation`, `campaign`, `plan`, `reference`, `tracking`, `decision`, `index`, `resource`, `meta`), then location tags, then domain tags.
- Limit to 2-5 tags per note.

**Sources:**
- Include the full source URL as an inline link at the point where it is first referenced in the body text.
- Add a `## Sources` section at the bottom listing all source URLs.
- Every factual claim from external research must be traceable to its source.

**Format matching:**
- If `action` is `update`, read the existing note first and merge new information into it. Expand sections. Never discard existing content.
- If the target `folder` contains existing notes (from `vault_context`), match their section structure and style.

**Media embeds:**
- If the note's `media` list is non-empty, embed media assets using Obsidian syntax: `![[path/to/asset]]` at the appropriate point in the content.

**Content:**
- For `create`: Write the complete note from scratch using the fetched source content and `content_summary` as your guide.
- For `update`: Merge new information into the existing note. Preserve and expand sections. Never remove existing content.

#### vi. Save the note

- `create`: Write to `VAULT/{folder}/{filename}` using the Write tool. Create the folder first if needed via Bash: `mkdir -p "VAULT/{folder}"`
- `update`: Write to the existing note path using the Write tool.

#### vii. Track the written note

Run via Bash:
```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import append_written_note
from pathlib import Path
append_written_note(Path('STATE_DIR'), 'TOPIC', 'NOTE_PATH', 'MODEL')
"
```

#### viii. Update progress

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import update_stage
from pathlib import Path
update_stage(Path('STATE_DIR'), 'write', {'total_notes': TOTAL, 'completed': COMPLETED, 'current': 'CURRENT_TITLE'})
"
```

### 8c. Update MOC files

After all notes are written:

1. If `vault_context.suggested_moc_update` is not null, read that MOC file and add/update entries for the notes written in this batch. Match the MOC's existing format exactly.

2. For each folder that received new notes, check if it contains a file starting with `_` or containing `MOC`, `Index`, `Hub`, or `Overview` that was not already processed. If found, update it too.

---

## Stage 8d: Wikilink Scan

After all notes and MOCs are written, scan for wikilink opportunities between the new notes and existing project notes.

### 8d-i. Refresh vault index

```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from vault_index import update_index
from pathlib import Path
stats = update_index(Path('VAULT'))
print(json.dumps(stats))
"
```

This ensures the newly written notes are indexed before the scanner queries the vault.

### 8d-ii. Determine project folder

From the written notes list, extract the common parent folder. For example, if notes were written to `Projects/Activism/BJU/Bob Jones University.md` and `Projects/Activism/BJU/GRACE Report on Bob Jones University.md`, the project folder is `Projects/Activism/BJU`.

### 8d-iii. Dispatch wikilink-scanner agent

Read the agent definition: `REPO/agents/wikilink-scanner.md`

Load the written notes list:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import load_stage_output
from pathlib import Path
written = load_stage_output(Path('STATE_DIR'), 'written_notes')
print(json.dumps(written))
"
```

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: The full contents of `agents/wikilink-scanner.md`, followed by a `---` separator, followed by:

```json
{
  "new_notes": [{list of {path, title} from written_notes}],
  "project_folder": "{project folder vault-relative path}",
  "vault_root": "VAULT",
  "scripts_dir": "SCRIPTS"
}
```

### 8d-iv. Parse and apply edits

The agent returns a JSON object with `edits` and `stats`.

For each edit in the `edits` array:
1. Read the target file using the Read tool
2. Find the first occurrence of `edit.find` in the file content, using `edit.context` for disambiguation if needed
3. Replace it with `edit.replace` using the Edit tool
4. If the `find` text is not found (perhaps already wikilinked or content changed), skip it and log a warning

### 8d-v. Report results

Log the results:
```
Wikilink scan: {stats.total_edits} edits applied
  New notes: +{stats.wikilinks_in_new_notes} wikilinks
  Existing notes: +{stats.wikilinks_in_existing_notes} wikilinks to new notes
```

If no edits were needed, log: `Wikilink scan: no new wikilinks needed.`

### 8d-vi. Update state

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import update_stage
from pathlib import Path
update_stage(Path('STATE_DIR'), 'discover')
"
```

---

## Stage 9: Discover

### 9a. Dispatch thread-discoverer agent

Read the agent definition: `REPO/agents/thread-discoverer.md`

Load the written notes list:
```bash
python -c "
import sys, json
sys.path.insert(0, 'SCRIPTS')
from state import load_stage_output
from pathlib import Path
written = load_stage_output(Path('STATE_DIR'), 'written_notes')
print(json.dumps(written))
"
```

Dispatch via the Task tool:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: The full contents of `agents/thread-discoverer.md`, followed by a `---` separator, followed by:

```json
{
  "project": "{project name}",
  "summaries": {the summaries items from Stage 6},
  "written_notes": {written notes list},
  "vault_root": "VAULT",
  "scripts_dir": "SCRIPTS"
}
```

### 9b. Parse thread proposals

The agent returns a JSON object with `threads` (sorted by score descending) and `batch_stats`.

### 9c. Present to user

Show the user:
```
Threads discovered from {project}:
{for each thread:}
  {index}. {topic} (score: {score}, {novelty_status})
     {rationale}
{end}

Batch stats: {total_entities_found} entities, {leads_above_threshold} leads above threshold

Research any of these? [1,2,3] / all / none
```

Wait for user response:
- **none:** Proceed to Stage 10.
- **all:** Save all threads as the next batch input.
- **specific numbers:** Save only the selected threads.

If threads are approved, save them to `STATE_DIR/approved_threads.json` for a follow-up `/research` invocation. Do NOT start a new pipeline run within this run.

---

## Stage 10: Complete

### 10a. Complete the run

```bash
python -c "
import sys
sys.path.insert(0, 'SCRIPTS')
from state import complete_run
from pathlib import Path
complete_run(Path('STATE_DIR'))
"
```

### 10b. Print summary

Collect all information from the pipeline and print:

```
Research complete: {project}

Created:
  - {path of each created note}

Updated:
  - {path of each updated note and MOC, or "none"}

Skipped:
  - {any notes skipped due to mtime conflict}

Warnings:
  - {fetch failures}
  - {media download failures}
  - {any other errors collected during the run}

{if threads approved:}
Threads queued for follow-up:
  - {list of approved thread topics}
  Run /research again to execute these.
{end}

Tier: {TIER} | Sources fetched: {count} | Notes written: {count}
```

---

## Error Handling

Throughout the pipeline, follow these principles:

1. **Failures do not stop the pipeline.** If a single fetch fails, a media download fails, or a summarization fails, log the error and continue. Collect all errors and report them in the final summary at Stage 10.

2. **State checkpoint after every stage.** Always call `update_stage()` before starting the next stage. If the pipeline crashes, the user can resume from the last checkpoint.

3. **Shared context by file path.** Write intermediate results to `STATE_DIR/` and reference them by path in agent prompts. Never duplicate large content blobs in agent prompts.

4. **Mtime checks before writing.** Always check if the target note was modified externally before overwriting. Skip and warn if it was.

5. **Atomic state updates.** Use `save_stage_output()` for all state file writes -- it uses temp file + rename for crash safety.

---

## Resume Flow

When resuming a run (Stage 1 detected an active run and the user chose "Resume"):

1. Read `current_run.json` to find the current `stage`.
2. Load any saved stage outputs (`research_plan.json`, `search_context.json`, `fetch_results.json`, `summaries.json`, `classification.json`, `written_notes.json`) from `STATE_DIR/`.
3. Skip to the recorded stage. For the `write` stage specifically, check `written_notes.json` to determine which notes are already complete and skip them.
4. Continue the pipeline from that point.

---
name: research
description: 'Research a topic or note and write results into the Obsidian vault. Usage: /research path/to/note.md  OR  /research "topic string". Runs as Sonnet; spawns Haiku agents for search and classification.'
---

# Research — Sonnet Orchestrator (3-Tier Pipeline)

## CRITICAL: Model Check

Before doing ANYTHING else, check your context window for your model identity.

Find the line: "You are powered by the model named..."

If that line is not present, OR if it does not say `claude-sonnet-4-6`:
- Output exactly: `ERROR: research requires claude-sonnet-4-6. Running on wrong model. Aborting.`
- Stop immediately.

Only continue past this point if you have confirmed you are Sonnet 4.6.

---

## Your Role

You orchestrate research into the vault using a 3-tier pipeline:
1. **Haiku search** — finds and evaluates URLs for a topic
2. **Python fetch** — fetches and caches page content via Jina Reader
3. **Haiku classify** — maps content to vault structure
4. **Sonnet write** — you synthesize and write the final notes

Vault root: `{{VAULT_ROOT}}`  <!-- Set to your Obsidian vault path -->
Scripts dir: `{{SCRIPTS_DIR}}`  <!-- Set to the research-workflow repo root (Python scripts are in scripts/ subfolder) -->
Python: `{{PYTHON_PATH}}`  <!-- Set to your Python 3.12+ executable path -->

---

## Step 1: Parse Input

The argument is everything after `/research `.

**If it looks like a file path** (contains `/` or `\` or ends in `.md`):
- Read the note at that path (relative to vault root)
- Extract `known_urls`: all `http://` or `https://` URLs in the note text
- Extract `topics`: headings, named campaigns, organizations, people, bill numbers, questions without a URL

**If it is a plain string:**
- `known_urls`: []
- `topics`: [the full input string]

---

## Step 2: Build Search Context

**Case A — Topics only (no known URLs):**

Read the `research-search` skill:
`{{HOME}}/.claude/skills/research-search/SKILL.md`

For each topic, spawn a Haiku agent:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: research-search skill content + this input block:

```
---
topic: [the topic string]
```

Wait for the response. Extract the JSON object from the response (first `{` to last `}`). If it starts with `ERROR:`, output it and stop.

Collect all `selected_urls` arrays from all topic responses into a combined list. Build a single `search_context` JSON with:
- `topic`: the first topic (or combined topic string if multiple)
- `query_used`: from the agent response
- `selected_urls`: combined deduplicated list
- `rejected_urls`: combined list
- `search_notes`: combined notes

**Case B — Known URLs only (no topics):**

Skip the Haiku search agent. Build `search_context` JSON directly:
```json
{
  "topic": "[derived from note title or first heading]",
  "query_used": "",
  "selected_urls": [
    { "url": "[each known_url]", "title": "", "snippet": "", "relevance_score": 10, "reason": "provided directly" }
  ],
  "rejected_urls": [],
  "search_notes": "URLs provided directly, search skipped"
}
```

**Case C — Both topics and known URLs:**

Run Case A for topics, then add the known URLs to `selected_urls` with `relevance_score: 10` and `reason: "provided directly"`.

---

## Step 3: Fetch Content via Python

Write the `search_context` JSON to a temporary file using the Write tool:
- Path: `{{SCRIPTS_DIR}}/.tmp/search_context.json`
- Create the `.tmp` directory if it doesn't exist (use Bash: `mkdir -p "{{SCRIPTS_DIR}}/.tmp"`)

Run the fetch script using Bash:
```bash
"{{PYTHON_PATH}}" "{{SCRIPTS_DIR}}/scripts/fetch_and_clean.py" --input "{{SCRIPTS_DIR}}/.tmp/search_context.json" --output "{{SCRIPTS_DIR}}/.tmp/fetch_results.json"
```

Wait for it to complete. If it exits with a non-zero code, output the stderr and stop.

Read `{{SCRIPTS_DIR}}/.tmp/fetch_results.json`.

If `fetched` is empty and `failed` is non-empty, output:
`Fetch failed for all URLs. Errors: [list failed[].error]`
Then stop.

If `failed` is non-empty but `fetched` is not empty, print a warning:
`Warning: Could not fetch: [list failed[].url]`
Then continue.

---

## Step 4: Classify via Haiku

Read the `research-classify` skill:
`{{HOME}}/.claude/skills/research-classify/SKILL.md`

Spawn a Haiku agent:
- `subagent_type`: `general-purpose`
- `model`: `haiku`
- `prompt`: research-classify skill content + the full contents of `fetch_results.json` appended after a `---` separator

Wait for the response. Extract the JSON object (first `{` to last `}`). If it starts with `ERROR:`, output it and stop.

If `notes_to_create` is empty, output:
`Classification returned no notes to create. Check fetch results for content quality.`
Then stop.

---

## Step 5: Write Notes

For each entry in `notes_to_create`:

### 5a. Prevent redundant notes

Before creating or updating, check for redundancy:

1. **Search for existing notes on the same topic.** Use Grep to search the vault:
   - Search by title keywords from the note's `title`
   - Search by abbreviation if the title includes one (e.g., search both "ALPR" and "Automatic License Plate Reader")
   - Search by location or organization name if relevant
2. **Check for stubs pointing elsewhere.** If you find an empty or near-empty stub (0-1 lines of content), check if a fuller version exists elsewhere in the vault. If so, delete the stub and update wikilinks to point to the full note.
3. **Merge if appropriate.** If similar notes exist:
   - Compare scope: Is one broader and the other more specific?
   - Decide: Keep one as primary and link from the other, or merge content
   - Update all wikilinks before deleting the redundant note
4. **Don't create bridge stubs.** Avoid empty wikilink targets as "bridges." Link directly to the full content note, using an alias if the name is long: `[[Full Note Title|display text]]`

### 5b. Read relevant files

Read all files in `vault_context.existing_notes_found` plus any notes referenced in `suggested_links`. Store contents keyed by path.

### 5c. Synthesize note content

Write the complete note content following ALL of these rules:

**Wikilinks:**
- Add `[[wikilinks]]` from `suggested_links` where the linked topic actually appears in the note content
- Scan the note content for mentions of existing vault notes (from the file list in Step 4) and add `[[wikilinks]]` to them
- For concepts in `stub_links` that don't have notes yet, add `[[stub wikilinks]]` and include a brief inline note about what to research (e.g., "[[Topic Name]] — worth investigating for connection to X"). **Do not create empty stub files.** Only create a stub file if it will contain at least a title, purpose statement, and TODO section.
- Use aliases for long titles: `[[Full Note Title|display text]]`
- Do not wikilink generic terms — only link specific, notable concepts worthy of their own note

**Tags:**
- Include tags in YAML frontmatter: `tags: [content-type, location, other-relevant-tags]`
- Start with a content-type tag from `suggested_tags`: research, legislation, campaign, plan, reference, tracking, decision, index, resource, meta
- Add location tags (greenville-sc, sc, etc.) if the content discusses specific places
- Add purpose prefixes (strategic-, tactical-) if the content informs decisions or implementation
- See `docs/TAGGING-REFERENCE.md` for complete tag list

**Sources:**
- Include the full source URL as an inline link at the point where it is first referenced
- Add a `## Sources` section at the bottom listing all `source_urls`
- Every factual claim from external research should be traceable to its source

**Format matching:**
- If `action` is `update` or `folder` contains existing notes, match their section structure exactly
- For campaign notes: match the format of existing campaign notes in that folder

**For `create`:** Write the complete new note from scratch using `content_summary` as your guide.

**For `update`:** Merge new information into the existing note. Expand sections. Never discard existing content.

### 5d. Write the note

- `create`: Write to `{{VAULT_ROOT}}/{folder}/{filename}`
- `update`: Overwrite the existing note path

### 5e. Update MOC notes

If `suggested_moc_update` is not null, read that MOC file and add/update an entry for the note just written. Match the MOC's existing format exactly.

Also check if the folder containing the target note has any file starting with `_` or containing `MOC`, `Index`, `Hub`, or `Overview` that wasn't already in `existing_notes_found` — if so, update it too.

---

## Step 6: Print Summary

```
Research complete.

Created:
  - [path of each created note, or "none"]

Updated:
  - [path of each updated note and MOC, or "none"]

Warnings:
  - [any fetch failures or issues, or "none"]
```

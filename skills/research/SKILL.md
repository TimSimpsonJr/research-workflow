---
name: research
description: Research a topic or note and write results into the Obsidian vault. Usage: /research path/to/note.md  OR  /research "topic string". Runs as Sonnet; spawns Haiku agents for search and classification.
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

Vault root: `C:\Users\tim\OneDrive\Documents\Tim's Vault`
Scripts dir: `C:\Users\tim\OneDrive\Documents\Projects\research-workflow`
Python: `C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe`

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
`C:\Users\tim\.claude\skills\research-search\SKILL.md`

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
- Path: `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\search_context.json`
- Create the `.tmp` directory if it doesn't exist (use Bash: `mkdir -p "C:/Users/tim/OneDrive/Documents/Projects/research-workflow/.tmp"`)

Run the fetch script using Bash:
```bash
"C:\Users\tim\AppData\Local\Programs\Python\Python312\python.exe" "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\fetch_and_clean.py" --input "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\search_context.json" --output "C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\fetch_results.json"
```

Wait for it to complete. If it exits with a non-zero code, output the stderr and stop.

Read `C:\Users\tim\OneDrive\Documents\Projects\research-workflow\.tmp\fetch_results.json`.

If `fetched` is empty and `failed` is non-empty, output:
`Fetch failed for all URLs. Errors: [list failed[].error]`
Then stop.

If `failed` is non-empty but `fetched` is not empty, print a warning:
`Warning: Could not fetch: [list failed[].url]`
Then continue.

---

## Step 4: Classify via Haiku

Read the `research-classify` skill:
`C:\Users\tim\.claude\skills\research-classify\SKILL.md`

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

### 5a. Read relevant files

Read all files in `vault_context.existing_notes_found` plus any notes referenced in `suggested_links`. Store contents keyed by path.

### 5b. Synthesize note content

Write the complete note content following ALL of these rules:

**Wikilinks:**
- Add `[[wikilinks]]` from `suggested_links` where the topic appears in the note
- Add `[[stub_links]]` for concepts in `stub_links` that don't have notes yet

**Tags:**
- Include `suggested_tags` in the frontmatter YAML

**Sources:**
- Include the full source URL inline at the point where first referenced
- Add a `## Sources` section at the bottom listing all `source_urls`

**Format matching:**
- If `action` is `update` or `folder` contains existing notes, match their section structure exactly
- For campaign notes: match the format of existing campaign notes in that folder

**For `create`:** Write the complete new note from scratch using `content_summary` as your guide.

**For `update`:** Merge new information into the existing note. Expand sections. Never discard existing content.

### 5c. Write the note

- `create`: Write to `C:\Users\tim\OneDrive\Documents\Tim's Vault\{folder}\{filename}`
- `update`: Overwrite the existing note path

### 5d. Update MOC notes

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

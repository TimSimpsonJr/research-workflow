> **DEPRECATED as of 2026-02-25.**
> This skill has been replaced by the 3-tier pipeline:
> - Tier 1 search: `research-search` skill
> - Tier 2 fetch: `fetch_and_clean.py` script
> - Tier 3 classify: `research-classify` skill
>
> This file is kept for rollback reference only. Do not invoke directly.
> The `research` orchestrator skill no longer references this file.

---
name: research-haiku
description: Haiku research and classification agent for the vault research workflow. Spawned internally by the research skill. Do not invoke directly.
---

# Research — Haiku Agent (Stage 1)

## CRITICAL: Model Check

Before doing ANYTHING else, check your system prompt for your model identity.

Find the line: "You are powered by the model named..."

If that line is not present in your system prompt, OR if it does not say `claude-haiku-4-5-20251001`:
- Output exactly: `ERROR: research-haiku requires claude-haiku-4-5-20251001. Running on wrong model. Aborting.`
- Stop immediately. Do not read files, fetch URLs, run searches, or take any other action.

Only continue past this point if you have confirmed you are Haiku.

---

## Your Role

**You must not write, create, edit, or delete any files at any point.**

**Do not output any text, narration, or explanation at any point during your work. Do not describe what you are doing. Do not summarize steps. Do not confirm actions. Your entire response — the only thing you output — is the single JSON object in Step 6. Nothing before it. Nothing after it.**

You are the research and classification agent. You will:
1. Fetch web content (known URLs and searched topics)
2. Map the vault file structure
3. Classify each article and match it to existing notes
4. Output a single raw JSON object — nothing else

---

## Input

You will receive:
- `vault_root` — absolute path to the vault
- `known_urls` — list of URLs already identified (may be empty)
- `topics` — list of research topics/questions (may be empty)

If both `known_urls` and `topics` are empty, skip Steps 3 and 4, and output `{"failures": [], "items": []}` immediately.

---

## Step 1: Build Vault File List

Use the Glob tool:
- Pattern: `**/*.md`
- Path: the vault_root value

Store the full list of relative file paths. If the Glob tool returns absolute paths, strip the vault_root prefix to obtain relative paths. You will use this list for matching and MOC discovery. Do not read the contents of any vault file at any point — use filenames only for all matching and classification decisions.

## Step 2: Discover MOC Notes

From the file list, flag files as potential MOC/index notes if they match ANY of:
- Filename starts with `_`
- Filename contains: `MOC`, `Index`, `Hub`, `Overview`, `Dashboard`, or `000`
- The file's immediate parent directory contains 5 or more `.md` files

Tag these for later — they are candidates to be updated alongside target notes.

## Step 3: Fetch Known URLs

For each URL in `known_urls`, attempt retrieval in this order:

1. **Direct fetch:** Use WebFetch on the original URL. If successful, extract main article text, truncate to 3000 words, store as `{ url, text }`, and move to the next URL.

2. **Wayback Machine fallback:** If the direct fetch fails (404, timeout, blocked, or empty content):
   - WebFetch `https://archive.org/wayback/available?url=[original_url]`
   - In the JSON response, find `archived_snapshots.closest.url`
   - If that field exists and `archived_snapshots.closest.status` is `200`, WebFetch that archived URL and use its content.

3. **Search fallback:** If both fetches fail, extract keywords from the URL slug (the last path segment — split on hyphens, remove stop words like "the", "a", "in", "to", "of"). Run a WebSearch with those keywords. Pick the most relevant result, WebFetch it, and use that content. Store the search-result URL (not the original) in `source_url` for this item.

4. **Give up:** If all three attempts fail, skip this URL entirely and add the original URL to `failures`.

## Step 4: Research Topics

For each topic in `topics`:
- Run 1–3 WebSearch queries (vary phrasing if first results are weak)
- Evaluate results — pick the 2–3 most relevant, credible pages
- Use WebFetch on each selected result
- Extract main article text
- Store as `{ url, text }` — truncate text to 3000 words if longer.

Use judgment: stop searching when you have enough material to write a useful note. Do not fetch more than 6 pages total across all topics.

## Step 5: Classify and Match Each Article

For each fetched article, determine:

**Content type:**
- `campaign` — a local/municipal effort to restrict, ban, remove, or oppose a surveillance technology or vendor
- `legislation` — a bill, ordinance, or law being proposed, amended, or passed
- `general_research` — background, analysis, journalism, organization profiles, or reference material

**Vault match:**
Scan the full file list for notes whose filenames closely match the article's subject (city name, campaign name, bill number, organization, person name).
- Close match found → `action: "update"`, `existing_note: relative/path`
- No match → `action: "create"`, `existing_note: null`

**Target path:**
- For `update`: use the exact existing note path
- For `create`: find the 2–3 most thematically similar notes in the file list and use their parent folder as the target directory. Follow the naming convention of notes in that folder (e.g., if similar notes are named `Austin TX Coalition.md`, name this one `Nashville TN.md`).

**Relevant files:**
Include notes that are:
- The matching/similar note (if found)
- 1–3 closely related notes in the same folder (for format reference)
- MOC notes discovered in Step 2 that live in the same folder area

Keep this list to 3–6 files. Do not include unrelated notes.

Flag each relevant file with `is_moc: true` if it was identified as a MOC in Step 2.

## Step 6: Output

Your entire response is a single JSON object. Follow these rules without exception:

- The very first character you output must be `{`
- The very last character you output must be `}`
- Do NOT use backticks. Do NOT use ```json or ``` fences. Do NOT wrap the JSON in any markdown.
- Do NOT write anything before the `{`. No step summaries, no "here is the result", no narration.
- Do NOT write anything after the `}`. No closing remarks, no notes.
- If all URLs failed and there are no items, still output the JSON: `{"failures": [...], "items": []}`

{
  "failures": ["https://failed-url.com"],
  "items": [
    {
      "source_url": "https://...",
      "article_text": "full extracted article text here",
      "content_type": "campaign | legislation | general_research",
      "relevant_files": [
        { "path": "relative/path/to/note.md", "is_moc": false },
        { "path": "relative/path/to/_Index.md", "is_moc": true }
      ],
      "action": "create | update",
      "existing_note": "relative/path/to/note.md or null",
      "target_path": "relative/path/to/New Note.md"
    }
  ]
}

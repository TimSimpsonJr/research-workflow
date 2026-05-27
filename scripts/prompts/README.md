# Prompts

Text templates used by the orchestrator and subagents.

## Assembly pattern

The orchestrator assembles prompts inline as:

```
{content}

---

{prompt_template}

---

{vault_rules}
```

`content` is the source material (article text, summary, etc.). `prompt_template` is one of the `.txt` files in this directory. `vault_rules` is `vault_rules.txt`, automatically appended to all writes/synthesis prompts. To skip vault rules for utility prompts (e.g., keyword extraction), omit `vault_rules` from the assembly.

## Files

- `vault_rules.txt` — shared rules for note creation (wikilinks, citations, tags). Auto-appended.
- `summarize.txt`, `summarize_fetch.txt`, `summarize_merge.txt` — summarization prompts (map and reduce).
- `extract_claims.txt`, `extract_transcript.txt` — extraction prompts.
- `identify_stakeholders.txt` — stakeholder extraction.
- `synthesize_topic.txt`, `find_related.txt` — synthesis prompts.
- `output_formats/` — downstream format templates (web_article, video_script, briefing, etc.).

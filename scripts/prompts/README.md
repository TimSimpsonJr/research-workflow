# Prompt Templates

These files are used as the trailing instruction in a single user-turn message.
The source content is prepended to the prompt text, separated by `\n\n---\n`.

Assembly pattern:
```
{source_content}

---
{prompt_template}
```

Scripts must use this pattern consistently. Never send these prompts as system messages.

## Vault Rules

`vault_rules.txt` contains shared rules for note creation (wikilinks, citations, tagging) that apply to all analysis and synthesis output. These rules are automatically appended after the prompt template by `claude_pipe.py` and all scripts that call `call_claude()` directly:

```
{source_content}

---
{prompt_template}

---
{vault_rules}
```

To skip vault rules (e.g., for utility prompts like keyword extraction), use `--no-vault-rules` with `claude_pipe.py` or omit the `load_vault_rules()` call in custom scripts.

Vault rules do **not** apply to raw ingestion (`ingest.py`) which archives source content without Claude processing.

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

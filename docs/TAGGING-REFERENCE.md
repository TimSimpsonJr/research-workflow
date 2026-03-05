# Tagging Reference

Every note in this vault should include tags in YAML frontmatter at the top:

```yaml
---
tags: [content-type, location, other-relevant-tags]
---
```

## Content-Type Tags (required — pick one)

| Tag | Use for |
|-----|---------|
| `research` | Background, analysis, journalism, reference material |
| `legislation` | Bills, ordinances, laws being proposed, amended, or passed |
| `campaign` | Local/municipal efforts to restrict, ban, or oppose something |
| `plan` | Strategic or tactical plans |
| `reference` | Evergreen reference material, glossaries, how-tos |
| `tracking` | Ongoing tracking of events, meetings, timelines |
| `decision` | Decision records, choices made and rationale |
| `index` | MOCs, hub notes, dashboards |
| `resource` | Tools, datasets, external resources |
| `meta` | Notes about the vault itself, workflows, templates |

## Location Tags (add when relevant)

Use when the note discusses specific places:

- **City-level:** `greenville-sc`, `spartanburg-sc`, `columbia-sc`
- **State-level:** `sc`, `nc`, `ga`
- **National:** `us-federal`

Format: `{city}-{state-abbr}` lowercase, hyphen-separated.

## Purpose Prefixes (add when relevant)

| Prefix | Use when |
|--------|----------|
| `strategic-` | The note informs high-level decisions or direction |
| `tactical-` | The note informs specific implementation or action steps |

Examples: `strategic-surveillance`, `tactical-foia`

## Area Prefix

Use `area-` only for genuinely ambiguous notes that span multiple categories:

- `area-privacy` — note covers privacy broadly, not one specific campaign or bill
- `area-policing` — general policing topic, not tied to a specific event

Avoid overusing `area-` — most notes should have a specific content-type tag instead.

## Examples

```yaml
# Research note about ALPR technology
tags: [research, greenville-sc, surveillance]

# A specific bill being tracked
tags: [legislation, sc, surveillance, strategic-privacy]

# Campaign to oppose facial recognition
tags: [campaign, greenville-sc, tactical-organizing]

# MOC for all surveillance-related notes
tags: [index, surveillance]

# General reference on FOIA procedures
tags: [reference, sc, tactical-foia]
```

## Quick Checklist

1. Does it have a content-type tag? (required)
2. Does it mention a specific place? Add a location tag.
3. Does it inform decisions or action? Add a purpose prefix tag.
4. Is it genuinely cross-cutting? Consider `area-` prefix.

# Researcher

Researcher is a Claude Code plugin that does real web research for you and files the results away as finished notes. Hand it one topic or a list of fifty, and a few minutes later your Obsidian vault has a handful of new notes waiting. Each one is searched, weighed for source quality, and cross-linked, then written to match how you already organize things: frontmatter, tags, `[[wikilinks]]`, and a sources section at the bottom.

It runs on Claude Code's own subagents (or a local model on your machine), so there's no separate API key to wire up and no per-search bill to watch.

## What you can do with it

- **Ask about anything.** `/researcher "the history of license plate readers in South Carolina"` and it comes back with a small, linked set of notes instead of 14 open browser tabs.
- **Hand it a whole list.** Point it at a file of topics and it works through all of them, not just the first few.
- **Run big batches in parallel.** Got 30 or 50 topics? Researcher fans them out and researches them at the same time instead of one after another, then writes them all into your vault. (This is the newest piece, built for people doing real volume.)
- **Let it find the next thread.** After a batch, it reads back over what it just wrote, spots the loose ends worth chasing, and offers to research those too.
- **Keep everything in one place.** New notes link to the notes you already have and live in your vault, not in a separate app.

## Why people like it

It weighs its sources. Every source gets a credibility rating, so a peer-reviewed paper or an official dataset counts for more than an anonymous blog post. A topic keeps gathering material until it has enough, or until it reaches a sensible stopping point.

For anything ambiguous or large, it presents the plan first, including a rough estimate of the time and tokens it will take, and waits for your approval before it runs.

It adds no cost beyond what you already pay for Claude. The work runs through Claude Code, with an optional local model (Ollama) handling summarization if you have one installed.

## Quick start

Install it from the Fieldwork marketplace:

```
/plugin marketplace add TimSimpsonJr/fieldwork-plugins
/plugin install researcher@fieldwork-plugins
```

Point it at your vault once:

```
/researcher-setup
```

Then research anything:

```
/researcher "any topic"
```

The setup wizard walks you through it step by step and never changes anything without asking first.

## The three ways to run it

- **One topic.** `/researcher "quantum computing"` researches a single topic start to finish.
- **A batch.** `/researcher batch topics.md` works through a list of topics from a file. Past about 10 topics, it automatically switches to the parallel batch engine.
- **Thread-pull.** After a batch, it suggests follow-up topics it found in your new notes, and you pick which ones to chase.

---

## Under the hood

The mechanics behind a run.

### Depth

The planner assigns each topic a depth, which sets how hard it digs before it stops:

| Depth        | Hop limit | Confidence target | Typical use                                 |
|--------------|-----------|-------------------|---------------------------------------------|
| `quick`      | 1         | 0.6               | a fast lookup or a small clarifying question |
| `standard`   | 3         | 0.7               | most everyday topics                         |
| `deep`       | 4         | 0.8               | technical or policy work that needs primaries |
| `exhaustive` | 5         | 0.9               | research-paper-grade coverage                |

### The research loop

Each topic runs a loop: search for sources (scored by credibility), fetch and clean the pages (with a cache so it never re-downloads the same thing), summarize them, then decide what to do next. The planner either keeps going down a chosen thread, stops because it has enough, or replans when the sources contradict each other or the coverage stalls. A quality check at the end can send a thin topic back around for another pass (up to twice) before it's flagged and moved on.

### Source ratings

Every source gets a tier from T1 (peer-reviewed work, primary documents, official datasets) down to T4 (opinion columns, personal blogs, social posts), plus a separate flag for whether it's a primary source. Confidence for a topic blends four things: how varied the source tiers are, how well the topic is covered, whether primary sources showed up, and whether there are enough sources overall. A second signal watches for contradictions and can trigger a replan on its own.

### Where notes go

Researcher hands the write-up to its companion plugin, [Librarian](https://github.com/TimSimpsonJr/librarian), which turns the research into proper vault notes: classified into the right folders, tagged, wikilinked to what you already have, with map-of-content pages kept up to date. (Librarian installs automatically alongside Researcher.)

### What it needs

Researcher runs on three tiers, and figures out which one you're on automatically:

| Tier     | You have                                            | You get                                                              |
|----------|-----------------------------------------------------|---------------------------------------------------------------------|
| **Base** | Claude Code (that's it)                             | The full pipeline, all through subagents                            |
| **Mid**  | Base, plus [Ollama](https://ollama.com)             | Summarizing happens on your machine                                 |
| **Full** | Mid, plus SearXNG, Playwright, yt-dlp, Whisper      | Private search, JavaScript-heavy pages, YouTube and audio transcription |

`/researcher-setup` checks what you have and can start the optional pieces for you.

### Project layout

See [MANIFEST.md](MANIFEST.md) for the full file tree and how the pieces fit together.

## For developers

```bash
pip install -r requirements.txt
pip install pytest pytest-mock
pytest tests/ -v
```

The Python suite is 389 tests, all offline, no API key needed. The batch workflow's JavaScript helpers have their own `node --test` suite (run `node --test` from the repo root).

**Requirements:** Python 3.10+, [Claude Code](https://docs.anthropic.com/en/docs/claude-code), and an [Obsidian](https://obsidian.md/) vault.

**Optional (full tier):** Docker (for SearXNG), Ollama, Playwright, `yt-dlp`, `openai-whisper`.

## License

MIT

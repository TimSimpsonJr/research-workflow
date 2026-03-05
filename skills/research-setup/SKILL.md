---
name: research-setup
description: 'Setup wizard for the research pipeline. Detects infrastructure, configures vault, installs optional tools. Run once per vault, re-run to update.'
---

# Research Setup Wizard

You are an interactive setup wizard. Walk the user through configuring the research pipeline step by step. Use **AskUserQuestion** at every decision point. Never install or modify anything without explicit user confirmation.

Scripts dir: `{{SCRIPTS_DIR}}`
Python: `{{PYTHON_PATH}}`

---

## Step 0: Load Existing Config (if any)

Before starting the wizard, check if the user already has a config.

Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from pathlib import Path
from config_manager import load_config
import json

# Try common locations — will be overridden once we know the vault path
# For now just report that we'll ask for the vault path first
print('READY')
"
```

If this fails, report the error and attempt to continue — the Python environment may need troubleshooting.

---

## Step 1: Vault Path

Ask the user for their Obsidian vault path.

Use **AskUserQuestion**:
```
Where is your Obsidian vault?

Options:
1. Enter the full path to an existing vault
2. Create a new template vault

If entering a path, provide the absolute path (e.g., C:\Users\you\Documents\My Vault or /home/you/vault).
```

**If the user provides a path:**
- Verify it exists using Bash: `test -d "USER_PATH" && echo "EXISTS" || echo "NOT_FOUND"`
- If not found, ask again
- Store as `VAULT_ROOT`

**If the user wants a template vault:**
- Ask where to create it (AskUserQuestion for a parent directory path)
- Create the template structure using Bash:
```bash
mkdir -p "PARENT/Research Vault/Inbox"
mkdir -p "PARENT/Research Vault/Areas"
mkdir -p "PARENT/Research Vault/Sources"
mkdir -p "PARENT/Research Vault/Resources"
mkdir -p "PARENT/Research Vault/assets"
mkdir -p "PARENT/Research Vault/Daily"
```
- Create a starter MOC at `PARENT/Research Vault/_Index.md`:
```markdown
---
title: Vault Index
tags: [index]
---

# Vault Index

## Areas

- [[Inbox]] — unsorted incoming notes

## Sources

Raw source material and ingested content.

## Resources

Reference material and evergreen notes.
```
- Store `PARENT/Research Vault` as `VAULT_ROOT`

**Check for existing config:**

Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from pathlib import Path
from config_manager import load_config
import json
config = load_config(Path(r'VAULT_ROOT'))
if config:
    print('EXISTING_CONFIG')
    print(json.dumps(config, indent=2))
else:
    print('NO_CONFIG')
"
```

If existing config is found, show the user its contents and ask:
```
Found existing configuration for this vault. Would you like to:
1. Update individual settings (re-run specific steps)
2. Start fresh (reconfigure everything)
```

If updating, skip steps where the user is happy with the current value. If starting fresh, proceed through all steps.

---

## Step 2: Scan Vault Conventions

Run a vault scan to detect existing note patterns. Use Bash:

```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from pathlib import Path
import re, json, os

vault = Path(r'VAULT_ROOT')

# 1. Folder structure
top_folders = sorted([
    d.name for d in vault.iterdir()
    if d.is_dir() and not d.name.startswith('.')
])

# 2. Sample notes for convention detection
md_files = list(vault.rglob('*.md'))
md_files = [f for f in md_files if not any(p.startswith('.') for p in f.relative_to(vault).parts)]

tag_formats = {'list': 0, 'string': 0, 'inline': 0, 'none': 0}
fm_fields = {}
moc_files = []

for f in md_files[:50]:
    try:
        text = f.read_text(encoding='utf-8')
    except:
        continue
    # Check for MOC patterns
    name = f.stem
    if name.startswith('_') or any(k in name for k in ['MOC', 'Index', 'Hub', 'Overview', 'Dashboard']):
        rel = str(f.relative_to(vault)).replace(os.sep, '/')
        moc_files.append(rel)
    # Frontmatter detection
    fm_match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for line in fm.splitlines():
            if ':' in line:
                key = line.split(':')[0].strip()
                fm_fields[key] = fm_fields.get(key, 0) + 1
            if line.strip().startswith('tags:'):
                rest = line.split(':', 1)[1].strip()
                if rest.startswith('['):
                    tag_formats['list'] += 1
                elif rest.startswith('-') or rest == '':
                    tag_formats['list'] += 1
                else:
                    tag_formats['string'] += 1
    # Inline tag detection
    inline_tags = re.findall(r'(?<!\w)#[a-zA-Z][a-zA-Z0-9_/-]+', text)
    if inline_tags and not fm_match:
        tag_formats['inline'] += 1

result = {
    'total_notes': len(md_files),
    'top_folders': top_folders,
    'tag_format_counts': tag_formats,
    'dominant_tag_format': max(tag_formats, key=tag_formats.get) if any(tag_formats.values()) else 'list',
    'frontmatter_fields': sorted(fm_fields.keys(), key=lambda k: -fm_fields[k])[:10],
    'moc_files': moc_files[:10],
    'moc_pattern': '^_|MOC|Index|Hub' if moc_files else '^_|MOC|Index'
}
print(json.dumps(result, indent=2))
"
```

Present the findings to the user:
```
Vault scan results:
- Total notes: {total_notes}
- Top-level folders: {top_folders}
- Tag format: {dominant_tag_format} (based on {count} sampled notes)
- Common frontmatter fields: {frontmatter_fields}
- MOC/Index notes found: {moc_files}

These conventions will be used to configure the pipeline. Anything look wrong?
```

Wait for acknowledgment via AskUserQuestion before proceeding.

---

## Step 3: Detect Platform

Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import get_platform_info
import json
print(json.dumps(get_platform_info(), indent=2))
"
```

Report to user:
```
Platform detected:
- OS: {os}
- Architecture: {arch}
- WSL: {is_wsl}
```

Store `platform_info` for later steps.

---

## Step 4: Ollama

Check if Ollama is installed. Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import check_ollama
import json
print(json.dumps(check_ollama(), indent=2))
"
```

**If installed and running:**
- Report: `Ollama is installed and running. Models available: {models}`
- Set `ollama_installed = True`
- Skip to Step 5

**If installed but not running:**
- Report: `Ollama is installed but the server is not running.`
- Ask user: `Would you like to start Ollama? (Run "ollama serve" in a separate terminal, then tell me when it's ready)`
- Set `ollama_installed = True`

**If not installed:**

Use AskUserQuestion:
```
Ollama is not installed. Ollama enables local AI model inference, which allows the mid and full tiers of the research pipeline.

Would you like to install it?
- The base tier works without Ollama (uses Claude API only)
- Mid/full tiers need Ollama for local classification and summarization
```

If the user says yes:
- **Linux or WSL**: Ask for confirmation, then run: `curl -fsSL https://ollama.com/install.sh | sh`
- **macOS**: Ask for confirmation, then run: `curl -fsSL https://ollama.com/install.sh | sh`
- **Windows (not WSL)**: Tell the user: `Download and install Ollama from https://ollama.com/download. Run the installer, then tell me when it's done.`

After installation, re-run the Ollama check to verify.

If the user declines, set `ollama_installed = False` and note that base tier will be used.

---

## Step 5: Hardware Check and Model Recommendation

Gather hardware info. Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import platform, subprocess, json, os

info = {'total_ram_gb': 0, 'gpu_vram_gb': 0, 'gpu_name': 'unknown'}

# RAM detection
system = platform.system()
if system == 'Windows':
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong),
                        ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong),
                        ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong),
                        ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        info['total_ram_gb'] = round(stat.ullTotalPhys / (1024**3), 1)
    except:
        pass
elif system == 'Darwin':
    try:
        out = subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True)
        info['total_ram_gb'] = round(int(out.strip()) / (1024**3), 1)
    except:
        pass
else:
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    kb = int(line.split()[1])
                    info['total_ram_gb'] = round(kb / (1024**2), 1)
                    break
    except:
        pass

# GPU VRAM detection via nvidia-smi
try:
    out = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=memory.total,name', '--format=csv,noheader,nounits'],
        text=True, timeout=5
    )
    line = out.strip().splitlines()[0]
    parts = line.split(',')
    info['gpu_vram_gb'] = round(int(parts[0].strip()) / 1024, 1)
    info['gpu_name'] = parts[1].strip()
except:
    # No NVIDIA GPU or nvidia-smi not available
    pass

print(json.dumps(info, indent=2))
"
```

Parse the hardware info and get a model recommendation. Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import recommend_model
import json
rec = recommend_model(RAM_GB, VRAM_GB)
print(json.dumps(rec, indent=2))
"
```

Replace `RAM_GB` and `VRAM_GB` with the values from the hardware check.

Present to user:
```
Hardware detected:
- RAM: {total_ram_gb} GB
- GPU: {gpu_name} ({gpu_vram_gb} GB VRAM)

Model recommendation: {model} — {reason}
```

**If Ollama is available and a model is recommended:**

Use AskUserQuestion:
```
Would you like to pull the recommended model ({model})?
This will download the model weights (several GB). You can also enter a different model name if you prefer.
```

If yes, pull the model via Bash:
```bash
ollama pull MODEL_NAME
```

After pull completes, offer a quick benchmark:
```
Model pulled successfully. Would you like to run a quick speed test?
This sends a short prompt to the model to measure response time.
```

If yes, run via Bash:
```bash
"{{PYTHON_PATH}}" -c "
import subprocess, time, json
start = time.time()
proc = subprocess.run(
    ['ollama', 'run', 'MODEL_NAME', 'Summarize this in one sentence: The quick brown fox jumps over the lazy dog.'],
    capture_output=True, text=True, timeout=120
)
elapsed_ms = round((time.time() - start) * 1000)
print(json.dumps({'elapsed_ms': elapsed_ms, 'output': proc.stdout.strip()[:200], 'success': proc.returncode == 0}))
"
```

Report the result and store `ollama_benchmark_ms`.

---

## Step 6: yt-dlp

Check availability. Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import check_ytdlp
import json
print(json.dumps(check_ytdlp(), indent=2))
"
```

**If installed:** Report `yt-dlp is available.` and set `ytdlp_available = True`.

**If not installed:**

Use AskUserQuestion:
```
yt-dlp is not installed. It's used for downloading YouTube videos and extracting audio for transcription.

Would you like to install it? (pip install yt-dlp)
```

If yes, run via Bash:
```bash
"{{PYTHON_PATH}}" -m pip install yt-dlp
```

Re-check after install. If the user declines, set `ytdlp_available = False`.

---

## Step 7: Whisper

Check availability. Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import check_whisper
import json
print(json.dumps(check_whisper(), indent=2))
"
```

**If installed:** Report `Whisper is available (backend: {backend}).` and set `whisper_available = True`.

**If not installed:** Report:
```
Whisper is not installed. It's used for audio transcription (YouTube videos, podcasts, interviews).

Installation is optional and requires significant disk space and compute resources.
To install later: pip install openai-whisper

Skipping for now.
```

Set `whisper_available = False`. Do not offer to auto-install — it's heavy.

---

## Step 8: SearXNG

Use AskUserQuestion:
```
Do you have a SearXNG instance running?

SearXNG provides private web search for the research pipeline's full tier.
- If you have one: provide the URL (e.g., http://localhost:8080)
- If not: the base tier will use Claude's built-in WebSearch tool instead

Enter the URL, or type "skip" to skip.
```

**If the user provides a URL:**

Test connectivity via Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import check_searxng
import json
print(json.dumps(check_searxng('USER_URL'), indent=2))
"
```

If reachable: `SearXNG is reachable at {url}.` Set `searxng_url`.
If not reachable: `Could not connect to SearXNG at {url}. Check that the server is running.` Ask user to retry or skip.

**If skip:** Set `searxng_url = None`.

---

## Step 9: Generate Config and Vault Rules

### 9a. Determine tier

Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from detect_tier import detect_tier
print(detect_tier(SEARXNG_URL_OR_NONE))
"
```

Replace `SEARXNG_URL_OR_NONE` with the SearXNG URL string (quoted) or `None`.

### 9b. Save config

Build the config dict from all collected values and save it. Use Bash:

```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from pathlib import Path
from config_manager import save_config
import json

config = {
    'vault_root': r'VAULT_ROOT',
    'inbox': 'INBOX_FOLDER',
    'assets': 'ASSETS_FOLDER',
    'moc_pattern': 'MOC_PATTERN',
    'tag_format': 'TAG_FORMAT',
    'date_format': '%Y-%m-%d',
    'frontmatter_fields': FRONTMATTER_FIELDS_LIST,
    'ollama_enabled': OLLAMA_BOOL,
    'ollama_model': OLLAMA_MODEL_OR_NONE,
    'ollama_benchmark_ms': BENCHMARK_OR_NONE,
    'searxng_url': SEARXNG_URL_OR_NONE,
    'whisper_available': WHISPER_BOOL,
    'ytdlp_available': YTDLP_BOOL,
    'tier': 'TIER',
}

save_config(Path(r'VAULT_ROOT'), config)
print('Config saved to VAULT_ROOT/.research-workflow/config.json')
print(json.dumps(config, indent=2))
"
```

Replace all placeholders with the actual values collected during the wizard. Use the detected values from Step 2 for `inbox` (default "Inbox" if an "Inbox" folder exists, otherwise the first folder that looks like an inbox), `assets`, `moc_pattern`, `tag_format`, and `frontmatter_fields`.

### 9c. Generate vault_rules.txt

Create `{{SCRIPTS_DIR}}/scripts/prompts/vault_rules.txt` using the Write tool. Base the content on the detected conventions:

```markdown
## Vault Rules

These rules apply to all notes written by the research pipeline.

### Frontmatter

Every note must start with YAML frontmatter:

---
title: Note Title
tags: [{tag_format} format — use brackets for list, bare for string]
source: URL or "local"
created: {date_format}
---

Common fields in this vault: {frontmatter_fields joined by comma}

### Tags

Use {tag_format} format in frontmatter.
Content-type tags (pick one): research, legislation, campaign, plan, reference, tracking, decision, index, resource, meta
Add location tags where relevant (e.g., greenville-sc, sc).
Add purpose prefixes where relevant (strategic-, tactical-).
See docs/TAGGING-REFERENCE.md for the complete taxonomy.

### Wikilinks

- Link to existing vault notes using [[Note Title]] when the topic is mentioned
- Use aliases for long titles: [[Full Title|short name]]
- Only link specific, notable concepts — not generic terms
- For concepts without notes yet, use [[Stub Link]] sparingly and only if the concept deserves its own note

### Sources

- Include source URLs as inline links at first reference
- Add a ## Sources section at the bottom of every research note
- Every factual claim from external research should trace to its source

### MOC Pattern

MOC notes in this vault match: {moc_pattern}
When creating notes in a folder with a MOC, update the MOC to include the new note.
```

Adjust the rules to match what was detected in Step 2. If no vault_rules.txt exists yet, create it. If one already exists, ask the user before overwriting.

---

## Step 10: Build Vault Index

Use Bash:
```bash
"{{PYTHON_PATH}}" -c "
import sys; sys.path.insert(0, '{{SCRIPTS_DIR}}/scripts')
from pathlib import Path
from vault_index import build_index, list_notes

vault = Path(r'VAULT_ROOT')
db_path = build_index(vault)
notes = list_notes(vault)
print(f'Index built at: {db_path}')
print(f'Notes indexed: {len(notes)}')
"
```

Report:
```
Vault index built successfully.
- Database: {db_path}
- Notes indexed: {count}
```

---

## Step 11: Summary

Print a clear summary of everything that was configured:

```
Setup complete!

Vault: {vault_root}
Tier: {tier} ({tier description})
  - base: Claude API only (WebSearch + Jina Reader)
  - mid: base + local Ollama models
  - full: mid + SearXNG private search

Platform: {os} ({arch})

Tools:
  - Ollama: {installed/not installed} {model if applicable}
  - yt-dlp: {available/not available}
  - Whisper: {available/not available}
  - SearXNG: {url or "not configured"}

Vault conventions:
  - Tag format: {tag_format}
  - Frontmatter fields: {fields}
  - MOC pattern: {moc_pattern}
  - Notes indexed: {count}

Config saved to: {vault_root}/.research-workflow/config.json
Vault rules saved to: {scripts_dir}/scripts/prompts/vault_rules.txt

Next steps:
  - Run /research "your topic" to start researching
  - Run /research path/to/note.md to research an existing note
```

If any issues were encountered (failed installs, missing tools), list them under a "Warnings" section.

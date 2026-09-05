# nxdo


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.2.26-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$2.81-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-19.2h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $2.8136 (36 commits)
- 👤 **Human dev:** ~$1922 (19.2h @ $100/h, 30min dedup)

Generated on 2026-07-07 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---

`nxdo` is a Python package that inspects the current project state, reads recent git history, adds a user question for an LLM, and returns a concrete plan for the next 10 engineering tasks.

**Documentation:** [docs/](docs/) · **Examples:** [examples/](examples/) · **Step-by-step guide:** [docs/how-it-works.md](docs/how-it-works.md)

## How it works (step by step)

1. **Analyze the repo** — README, manifests, tree, stack (`project_analyzer`)
2. **Read git context** — commits, changed files, TODO/FIXME markers (`git_reader`)
3. **Optional metrics** — complexity, coupling, hotspots (`metrics`)
4. **Build prompt** — snapshot + git + your `--extra-context` (`llm_client`)
5. **Call LLM** — OpenAI-compatible API, default OpenRouter (`providers`)
6. **Validate plan** — 10 tasks as Pydantic `TaskPlan` (`models`)
7. **Output** — terminal, JSON, TODO.md, or `.planfile/` (`tickets`, `auto`)

```bash
pip install nxdo
export OPENROUTER_API_KEY="your-key"

# 1–2: inspect context (no API cost)
nxdo print-context .

# 3: metrics only (no API cost)
nxdo metrics .

# 4–6: generate plan
nxdo plan . -e "What should we build next?"

# 7: export or sync tickets
nxdo plan . --json > plan.json
nxdo tickets . --sync-planfile
```

Real outputs from running nxdo **on this repo**: [examples/nxdo-self-plan.json](examples/nxdo-self-plan.json) · [examples/nxdo-self-plan.txt](examples/nxdo-self-plan.txt) · [examples/nxdo-self-context.txt](examples/nxdo-self-context.txt) · [examples/nxdo-self-prompt.txt](examples/nxdo-self-prompt.txt) · [examples/nxdo-self-metrics.txt](examples/nxdo-self-metrics.txt)

Verify: `./examples/check-examples.sh`

See the full walkthrough in [docs/how-it-works.md](docs/how-it-works.md).

## What is included

- **Project snapshot analysis** — README, manifests (pyproject.toml, package.json, Cargo.toml, …), directory tree, stack detection
- **Git context** — recent commits, most-changed files, TODO/FIXME markers
- **Advanced code metrics** — cyclomatic complexity, coupling analysis, bug hotspots, bus factor detection
- **Koru-aware planning** — Deep integration with koru framework for intelligent task generation
- **Pydantic models** — validated data models for tasks and plans (`Task`, `TaskPlan`)
- **Provider abstraction** — pluggable LLM backends; ships with an OpenAI-compatible provider (works with OpenRouter and any OpenAI-style API)
- **Planner orchestrator** — `generate_next_tasks()` composes analysis + prompt + LLM call into a validated TaskPlan
- **Rich CLI** — `nxdo plan`, `nxdo auto`, `nxdo metrics`, `nxdo print-context`, `nxdo print-prompt`, `nxdo validate`, `nxdo tickets`
- **Reliability** — `httpx` for HTTP, `tenacity` for automatic retry/backoff, `pydantic-settings` for environment config

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
nxdo print-prompt .
```

To generate a real plan, set `OPENROUTER_API_KEY` or `OPENAI_API_KEY` and run:

```bash
nxdo plan . --extra-context "What should we build next for this repository?"
```

Output as JSON:

```bash
nxdo plan . --json
```

Inspect captured project and git context without calling the LLM:

```bash
nxdo print-context .
```

Validate a saved plan file:

```bash
nxdo validate plan.json
```

Analyze code metrics and coupling:

```bash
nxdo metrics .
```

## CLI Reference

### `nxdo plan`
Generate a 10-task engineering plan for a repository.

**Usage:**
```bash
nxdo plan [REPO_PATH] [OPTIONS]
```

**Options:**
- `--extra-context, -e TEXT`: Additional prompt context for the LLM
- `--model, -m TEXT`: Override the LLM model name
- `--base-url TEXT`: Override the API base URL
- `--json`: Output plan as JSON instead of formatted text
- `--max-commits INTEGER`: How many recent commits to inspect (default: 30)

### `nxdo print-context`
Print the assembled project and git context without calling the LLM.

**Usage:**
```bash
nxdo print-context [REPO_PATH] [OPTIONS]
```

**Options:**
- `--max-commits INTEGER`: How many recent commits to inspect (default: 30)
- `--raw`: Print raw text instead of Rich panels

### `nxdo print-prompt`
Print the full prompt that would be sent to the LLM.

**Usage:**
```bash
nxdo print-prompt [REPO_PATH] [OPTIONS]
```

**Options:**
- `--extra-context, -e TEXT`: Additional prompt context for the LLM
- `--max-commits INTEGER`: How many recent commits to inspect (default: 30)

### `nxdo validate`
Validate a saved JSON plan file against the TaskPlan schema.

**Usage:**
```bash
nxdo validate PLAN_FILE
```

### `nxdo auto`
Auto-generate and sync tickets for the most important work. This is the quickest way to get actionable tickets into your planfile.

**Usage:**
```bash
nxdo auto [REPO_PATH] [OPTIONS]
```

**What it does:**
1. Analyzes project for high-priority issues (hotspots, complexity, coupling)
2. Generates tickets using koru-aware planning
3. Auto-syncs to `.planfile/` for execution via koru queue

**Options:**
- `--extra-context, -e TEXT`: Additional prompt context for the LLM
- `--dry-run`: Show what would be done without executing

**Example:**
```bash
# Quick auto mode - analyze, generate, sync
nxdo auto

# With extra context
nxdo auto . -e "Focus on security improvements"

# Dry run to preview
nxdo auto --dry-run
```

**Equivalent to:**
```bash
nxdo tickets . --koru-aware --sync-planfile
```

### `nxdo metrics`
Display comprehensive code metrics for the project including cyclomatic complexity, change coupling, bug hotspots, and bus factor analysis.

**Usage:**
```bash
nxdo metrics [REPO_PATH] [OPTIONS]
```

**Options:**
- `--top, -n INTEGER`: Show top N items per category (default: 10)
- `--min-coupling FLOAT`: Minimum coupling score to display (default: 0.3)

**Metrics displayed:**
- **Cyclomatic Complexity** per file (identify complex functions to refactor)
- **Coupling Analysis** — which files change together frequently (plan refactors together)
- **Coupling Clusters** — groups of tightly coupled files (sprint planning)
- **Bug Hotspots** — files with high bug fix rate and code churn
- **Bus Factor** — files with few authors (knowledge silos)

**Example:**
```bash
# Show metrics for current project
nxdo metrics .

# Show top 5 with higher coupling threshold
nxdo metrics . --top 5 --min-coupling 0.5
```

### `nxdo tickets`
Generate tickets from a plan using planfile integration.

This command generates tickets from a TaskPlan and optionally syncs them to TODO.md, .planfile/, or exports to planfile YAML format.

**Usage:**
```bash
nxdo tickets [REPO_PATH] [OPTIONS]
```

**Options:**
- `--extra-context, -e TEXT`: Additional prompt context for the LLM
- `--model, -m TEXT`: Override the LLM model name
- `--base-url TEXT`: Override the API base URL
- `--max-commits INTEGER`: How many recent commits to inspect (default: 30)
- `--sync-todo`: Append generated tasks to TODO.md as `- [ ]` checkboxes inside a managed `<!-- nxdo:generated-tasks -->` block (manual content is preserved; repeated runs replace the block idempotently)
- `--sync-planfile`: Store tickets in .planfile/ and sync with markdown
- `--export-yaml`: Export to planfile YAML format
- `--output, -o PATH`: Output file for YAML export
- `--koru-aware`: Enable koru integration schema for smart task planning

**Examples:**
```bash
# Generate and display tickets
nxdo tickets .

# Sync to TODO.md
nxdo tickets . --sync-todo

# Export to planfile YAML
nxdo tickets . --export-yaml --output strategy.yaml

# Koru-aware planning (generates tasks referencing koru operations)
nxdo tickets . --koru-aware --sync-planfile
```

**Note:** This feature requires the planfile package. It will be auto-installed if missing.

## Configuration

All settings are read from environment variables:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | API key for OpenRouter (preferred) |
| `OPENAI_API_KEY` | — | API key for OpenAI-compatible endpoint |
| `LLM_MODEL` | `openrouter/qwen/qwen3-coder-next` | Model name |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | API base URL |
| `LLM_TIMEOUT` | `60` | HTTP timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Number of retry attempts on network error |
| `MAX_COMMITS` | `30` | How many recent commits to read |

## Runtime dependencies

- `pydantic>=2`
- `pydantic-settings>=2`
- `typer>=0.12`
- `rich>=13`
- `httpx>=0.27`
- `tenacity>=8`

## Examples

### Generate a plan for a Python project
```bash
export OPENROUTER_API_KEY="your-api-key"
nxdo plan /path/to/project --extra-context "Focus on improving test coverage"
```

### Use a custom model
```bash
nxdo plan . --model "openrouter/anthropic/claude-3.5-sonnet"
```

### Inspect what data is sent to the LLM
```bash
nxdo print-prompt . --extra-context "Review security issues"
```

### Generate a plan and save as JSON
```bash
nxdo plan . --json > plan.json
nxdo validate plan.json
```

### Analyze a project with limited git history
```bash
nxdo plan . --max-commits 10
```

### Quick auto mode (analyze + generate + sync)

```bash
# One command to analyze project and create tickets in planfile
nxdo auto

# With custom focus
nxdo auto . -e "Refactor authentication system"
```

### Code metrics analysis

```bash
# Full metrics report
nxdo metrics .

# High coupling files
nxdo metrics . --top 10 --min-coupling 0.6
```

### Koru-aware planning

```bash
nxdo tickets . --koru-aware --sync-planfile
```

## Architecture

### Modules

- **nxdo.project_analyzer** — Project analysis (manifests, structure, stack)
- **nxdo.git_reader** — Git history analysis
- **nxdo.metrics** — Code metrics (complexity, coupling, hotspots)
- **nxdo.koru_context** — Koru framework integration
- **nxdo.planner** — Orchestrates analysis → LLM → TaskPlan
- **nxdo.providers** — Pluggable LLM backends
- **nxdo.ticket_generator** — Planfile integration

### Docs and examples

- [docs/README.md](docs/README.md) — documentation index
- [docs/how-it-works.md](docs/how-it-works.md) — pipeline and step-by-step tutorial
- [examples/](examples/) — sample outputs from self-analysis

## Development

```bash
pip install -e ".[dev]"
PYTHONPATH=src python -m unittest discover -s tests -v
```


## Changelog

### 0.2.x
- **Added** `nxdo auto` command — one-command workflow (analyze + generate + sync)
- **Added** `nxdo metrics` command (complexity, coupling, hotspots, bus factor)
- **Added** `--koru-aware` flag for koru-integrated planning
- **Added** `nxdo.metrics` module
- **Added** `nxdo.koru_context` module
- **Renamed** package from `lane` to `nxdo` on PyPI and GitHub
- **Improved** Test coverage to 97%
- **Improved** Refactored CC hotspots

## License

Licensed under Apache-2.0.

## Dependency maintenance

See [internal dependency updates](docs/dependencies.md) for daily updates, locked tests and Python support.

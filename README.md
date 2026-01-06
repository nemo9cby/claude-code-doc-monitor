# Documentation Monitor

Monitor Anthropic documentation (Claude Code and API docs) for updates with Telegram notifications and GitHub Pages diff reports.

## Supported Documentation Sources

| Source | URL | Description |
|--------|-----|-------------|
| Claude Code | `code.claude.com/docs` | Claude Code CLI documentation |
| Anthropic API | `platform.claude.com/docs` | Anthropic API/SDK documentation |

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and set your credentials:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OPENROUTER_API_KEY=your_api_key  # For LLM analysis
```

## Usage

```bash
# Monitor all sources
python -m src.main

# Monitor specific source only
python -m src.main --source claude-code
python -m src.main --source anthropic-api

# Skip notifications (for testing)
python -m src.main --no-notify
```

## Testing

### Unit Tests

```bash
pytest tests/ -v --ignore=tests/e2e
```

### E2E Tests

The E2E tests use a **completely isolated environment** to avoid impacting production data:

| Resource | Production | E2E Test |
|----------|------------|----------|
| Source URL | Real docs sites | `http://localhost:8765/test-docs` |
| Docs Storage | `docs/{source}/` | `tests/e2e/.test_output/docs/test/` |
| Reports | `reports/` | `tests/e2e/.test_output/reports/` |

#### Running E2E Tests

```bash
# Run E2E tests (skip real Telegram notification)
pytest tests/e2e/ -v -m "e2e and not real_telegram"

# Run ALL E2E tests including real Telegram notification
pytest tests/e2e/ -v -m "e2e"

# Preserve test output for inspection
PRESERVE_E2E_OUTPUT=1 pytest tests/e2e/ -v -m "e2e"
```

#### E2E Test Flow

1. **test_01**: Initial fetch stores baseline (v1 content)
2. **test_02**: Second run detects no changes
3. **test_03**: Content switches to v2, changes detected, reports generated
4. **test_04**: LLM analysis runs (requires `OPENROUTER_API_KEY`)
5. **test_05**: Real Telegram notification sent (requires Telegram credentials)

### All Tests

```bash
# Lint, format, and test
ruff check --fix . && ruff format . && pytest -xvs
```

## Architecture

```
src/
├── main.py       # CLI and orchestration
├── config.py     # Multi-source configuration
├── fetcher.py    # Async HTTP fetcher
├── differ.py     # Diff generation
├── analyzer.py   # LLM-powered diff analysis
├── reporter.py   # HTML report generation
└── notifier.py   # Telegram notifications

config/
├── config.yaml              # Main config with sources
└── pages/
    ├── claude-code.yaml     # Claude Code pages
    └── anthropic-api.yaml   # Anthropic API pages

docs/
├── claude-code/             # Stored Claude Code docs
└── anthropic-api/           # Stored Anthropic API docs
```

## Adding a New Documentation Source

1. Add source to `config/config.yaml`:
```yaml
sources:
  my-new-source:
    name: "My New Source"
    base_url: "https://example.com/docs"
    language: "en"
    docs_dir: "docs/my-new-source"
    pages_file: "config/pages/my-new-source.yaml"
```

2. Create pages file at `config/pages/my-new-source.yaml`:
```yaml
pages:
  - intro
  - getting-started
  - api-reference
```

3. The monitor will fetch `{base_url}/{language}/{page}.md` for each page.

## GitHub Actions

The monitor runs hourly via `.github/workflows/monitor.yml` and:
1. Fetches all configured documentation pages from all sources
2. Compares with previously stored versions
3. Generates HTML diff reports (published to GitHub Pages)
4. Sends Telegram notification if changes detected (grouped by source)
5. Commits updated docs and reports

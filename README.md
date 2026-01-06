# Claude Code Documentation Monitor

Monitor Claude Code documentation for updates with Telegram notifications and GitHub Pages diff reports.

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
# Run the monitor
python -m src.main

# Or use the CLI
doc-monitor
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
| Source URL | `https://code.claude.com/docs` | `http://localhost:8765/test-docs` |
| Docs Storage | `docs/en/` | `tests/e2e/.test_output/docs/test/` |
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

#### Inspecting E2E Results

After running with `PRESERVE_E2E_OUTPUT=1`, view reports at:
```
tests/e2e/.test_output/reports/YYYY/MM/DD/index.html
```

### All Tests

```bash
# Lint, format, and test
ruff check --fix . && ruff format . && pytest -xvs
```

## Architecture

```
src/
├── main.py       # CLI and orchestration
├── fetcher.py    # Async HTTP fetcher
├── differ.py     # Diff generation
├── analyzer.py   # LLM-powered diff analysis
├── reporter.py   # HTML report generation
├── notifier.py   # Telegram notifications
└── config.py     # Configuration loading

config/
├── config.yaml      # Production config
├── pages.yaml       # Pages to monitor
├── test_config.yaml # E2E test config
└── test_pages.yaml  # E2E test pages
```

## GitHub Actions

The monitor runs hourly via `.github/workflows/monitor.yml` and:
1. Fetches all configured documentation pages
2. Compares with previously stored versions
3. Generates HTML diff reports (published to GitHub Pages)
4. Sends Telegram notification if changes detected
5. Commits updated docs and reports

# Claude Code Documentation Monitor - Project Summary

## Overview

A Python-based monitoring system that tracks changes to Claude Code documentation, generates HTML diff reports, and sends Telegram notifications when updates are detected.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions (Hourly)                      │
├─────────────────────────────────────────────────────────────────┤
│  1. Checkout repo                                                │
│  2. Run monitor (python -m src.main)                            │
│  3. Commit & push changes                                        │
│  4. Deploy to GitHub Pages                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Monitor Pipeline                          │
├──────────────┬──────────────┬───────────────┬───────────────────┤
│   Fetcher    │    Differ    │   Reporter    │     Notifier      │
│              │              │               │                   │
│ Async HTTP   │ Compute diff │ Generate HTML │ Send Telegram     │
│ httpx        │ difflib      │ Jinja2        │ python-telegram   │
│ 49 pages     │ diff-match   │ templates     │ bot               │
└──────────────┴──────────────┴───────────────┴───────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Outputs                                 │
├─────────────────────────────────────────────────────────────────┤
│  • docs/en/*.md        - Stored markdown files                  │
│  • reports/YYYY/MM/DD/ - HTML diff reports per day              │
│  • meta.json           - Batch metadata (multiple runs/day)     │
│  • GitHub Pages        - Public diff viewer                     │
│  • Telegram messages   - Real-time notifications                │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Configuration (`src/config.py`)
- Loads settings from `config/config.yaml`
- Environment variables for secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- Configurable: concurrency, timeouts, retry counts

### 2. Fetcher (`src/fetcher.py`)
- Async HTTP client using `httpx`
- Fetches markdown from `https://code.claude.com/docs/en/{page}.md`
- 5 concurrent connections, 0.5s delay between requests
- Automatic retries on failure

### 3. Differ (`src/differ.py`)
- Computes differences between old and new content
- Generates unified diff (text) and HTML diff (visual)
- Tracks added/removed line counts

### 4. Reporter (`src/reporter.py`)
- Generates HTML reports using Jinja2 templates
- Directory structure: `reports/YYYY/MM/DD/`
- **Multiple batches per day**: Accumulates changes from multiple runs
- Each batch shows timestamp (e.g., "21:56 UTC")

### 5. Notifier (`src/notifier.py`)
- Sends Telegram notifications via Bot API
- HTML formatted messages with clickable links
- Lists up to 10 changed pages per notification

### 6. Main Orchestrator (`src/main.py`)
- CLI using Click and Rich for output
- Coordinates: fetch → diff → report → notify
- Handles errors gracefully

## GitHub Actions Workflow

```yaml
# .github/workflows/monitor.yml
on:
  schedule:
    - cron: '0 * * * *'  # Every hour
  workflow_dispatch:      # Manual trigger

jobs:
  monitor:
    - Checkout repository
    - Setup Python 3.12
    - Install dependencies
    - Run monitor
    - Commit and push changes

  deploy-pages:
    - Deploy reports/ to GitHub Pages
```

## Key Features

### Multiple Batches Per Day
When the monitor runs multiple times per day and detects changes, each run creates a separate "batch" with its timestamp. All batches are accumulated under the same day's report.

Example daily index:
```
Changes on 2026-01-03
2 total changes in 2 runs

21:56 UTC
  • overview.md    -1 line

21:57 UTC
  • quickstart.md  -1 line
```

### Telegram Notifications
```
Claude Code Docs Updated (2026-01-03)

1 page changed

Changed Pages:
• hooks: +577 lines, -520 lines

View Full Diff Report
```

## File Structure

```
claude-code-doc-monitor/
├── src/
│   ├── __init__.py
│   ├── config.py      # Configuration loader
│   ├── fetcher.py     # Async HTTP fetcher
│   ├── differ.py      # Diff computation
│   ├── reporter.py    # HTML report generator
│   ├── notifier.py    # Telegram notifications
│   └── main.py        # CLI orchestrator
├── tests/
│   ├── test_config.py
│   ├── test_fetcher.py
│   ├── test_differ.py
│   ├── test_reporter.py
│   ├── test_notifier.py
│   └── test_main.py
├── templates/
│   ├── page_diff.html
│   ├── daily_index.html
│   └── main_index.html
├── config/
│   ├── config.yaml
│   └── pages.yaml
├── docs/en/           # Stored markdown files
├── reports/           # Generated HTML reports
├── .github/workflows/
│   └── monitor.yml
├── pyproject.toml
└── CLAUDE.md
```

## Testing

- **59 tests** covering all modules
- Test-Driven Development (TDD) approach
- Uses pytest, pytest-asyncio, pytest-mock, respx

```bash
# Run all tests
pytest -xvs

# With coverage
pytest --cov=src --cov-report=term-missing
```

## Deployment

### GitHub Pages
Reports are automatically deployed to:
https://nemo9cby.github.io/claude-code-doc-monitor/

### Telegram Bot
- Created via @BotFather
- Token stored in GitHub Secrets
- Chat ID for notification delivery

## Development Timeline

1. **Project Setup**: pyproject.toml, dependencies, directory structure
2. **Config Module**: YAML loading, environment variables
3. **Fetcher Module**: Async HTTP with retries
4. **Differ Module**: Unified and HTML diff generation
5. **Reporter Module**: Jinja2 templates, date-based directories
6. **Notifier Module**: Telegram Bot API integration
7. **Main CLI**: Click-based orchestrator
8. **GitHub Actions**: Hourly cron, auto-deploy
9. **Enhancements**:
   - Timestamps instead of just dates
   - Fixed Telegram HTML links
   - Multiple batches per day accumulation

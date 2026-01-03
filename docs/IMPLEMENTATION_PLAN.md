# Claude Code Documentation Monitor - Implementation Plan

## Overview

Build a Python-based system to monitor Claude Code documentation for updates, with Telegram notifications and GitHub Pages-hosted diff reports.

**Key Discovery**: The docs site provides:
- `https://code.claude.com/docs/llms.txt` - Lists all 49 page URLs
- `https://code.claude.com/docs/en/{page}.md` - Returns page as markdown (no scraping needed!)

---

## Project Structure

```
claude-code-doc-monitor/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration loader (YAML + env vars)
│   ├── fetcher.py         # Async HTTP fetcher using httpx
│   ├── differ.py          # Diff engine (difflib + diff-match-patch)
│   ├── reporter.py        # HTML report generator (Jinja2)
│   ├── notifier.py        # Telegram bot integration
│   └── main.py            # Main orchestrator
├── templates/
│   ├── page_diff.html     # Individual diff page template
│   ├── daily_index.html   # Daily report index
│   └── main_index.html    # Main dashboard
├── docs/en/               # Stored markdown snapshots
├── reports/               # Generated HTML diff reports (GitHub Pages)
│   ├── index.html
│   └── css/diff.css
├── config/
│   ├── config.yaml
│   └── pages.yaml         # List of 49 pages from llms.txt
├── .github/workflows/
│   └── monitor.yml        # Daily cron + GitHub Pages deploy
├── requirements.txt
├── .env.example
├── SETUP_TELEGRAM.md
└── README.md
```

---

## Dependencies

```
httpx>=0.27.0              # Async HTTP client
python-telegram-bot>=21.0  # Telegram integration
diff-match-patch>=20230430 # Semantic HTML diffs
Jinja2>=3.1.0              # HTML templating
PyYAML>=6.0                # Config files
python-dotenv>=1.0.0       # Environment variables
click>=8.1.0               # CLI interface
rich>=13.0.0               # Pretty console output
```

---

## Implementation Steps

### Step 1: Project Setup
- Initialize project with `pyproject.toml`
- Create `requirements.txt`
- Set up directory structure
- Create `.gitignore`, `.env.example`

### Step 2: Configuration Module (`src/config.py`)
- Load settings from `config/config.yaml`
- Load secrets from environment variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)
- Parse page list from `config/pages.yaml`
- Dataclasses: `Config`, `TelegramConfig`, `FetcherConfig`

### Step 3: Fetcher Module (`src/fetcher.py`)
- Async HTTP client with `httpx`
- Fetch markdown via `{base_url}/en/{page}.md`
- Rate limiting (5 concurrent, 0.5s delay)
- Retry logic with exponential backoff
- Return `FetchResult(page_slug, content, status_code, error)`

### Step 4: Differ Module (`src/differ.py`)
- Compare old vs new content
- Generate unified diff (text) using `difflib`
- Generate HTML diff using `diff-match-patch`
- Calculate statistics (added/removed lines)
- Return `DiffResult(page_slug, has_changes, unified_diff, html_diff, summary)`

### Step 5: Reporter Module (`src/reporter.py`)
- Jinja2 templates for HTML reports
- Date-based directory structure: `reports/YYYY/MM/DD/`
- Generate individual page diffs
- Generate daily index page
- Update main dashboard with all report dates
- CSS styling with dark mode support

### Step 6: Notifier Module (`src/notifier.py`)
- `python-telegram-bot` async integration
- Format message with HTML:
  - Title: "Claude Code Docs Updated (YYYY-MM-DD)"
  - Summary: "X pages changed"
  - List of changed pages with links
  - Link to full diff report on GitHub Pages
- Handle message truncation (4096 char limit)
- Error notification support

### Step 7: Main Orchestrator (`src/main.py`)
1. Load configuration
2. Fetch all 49 pages concurrently
3. Compare each page with stored version
4. Save updated pages to `docs/en/`
5. Generate HTML diff reports
6. Git commit changes
7. Send Telegram notification
8. CLI interface with `click`

### Step 8: GitHub Actions Workflow

```yaml
name: Monitor Claude Code Docs
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - run: python -m src.main
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - name: Commit and push changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/ reports/
          git diff --staged --quiet || git commit -m "docs: update $(date +%Y-%m-%d)"
          git push

  deploy-pages:
    needs: monitor
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: reports/
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### Step 9: Telegram Bot Setup Guide
- Create bot via @BotFather
- Get bot token
- Get chat ID via `/getUpdates` API
- Configure secrets in GitHub repo

### Step 10: Documentation
- README.md with setup instructions
- SETUP_TELEGRAM.md guide

---

## Critical Files to Create

| File | Purpose |
|------|---------|
| `src/main.py` | Main entry point, orchestrates workflow |
| `src/fetcher.py` | Downloads markdown from docs site |
| `src/differ.py` | Computes text and HTML diffs |
| `src/reporter.py` | Generates HTML reports |
| `src/notifier.py` | Sends Telegram notifications |
| `src/config.py` | Loads and validates configuration |
| `config/pages.yaml` | List of 49 pages to monitor |
| `.github/workflows/monitor.yml` | Cron job + Pages deployment |
| `templates/page_diff.html` | Jinja2 template for diff pages |
| `reports/css/diff.css` | Styling for diff reports |

---

## Telegram Notification Format

```
Claude Code Docs Updated (2026-01-03)

3 pages changed

Changed Pages:
- overview: +12 lines, -3 lines
- quickstart: +5 lines
- hooks: Minor formatting changes

View Full Diff Report:
https://username.github.io/claude-code-doc-monitor/2026/01/03/
```

---

## Configuration

**config/config.yaml:**
```yaml
source:
  base_url: "https://code.claude.com/docs"
  language: "en"

storage:
  docs_dir: "docs"
  reports_dir: "reports"

telegram:
  enabled: true
  # bot_token: Set via TELEGRAM_BOT_TOKEN env var
  # chat_id: Set via TELEGRAM_CHAT_ID env var

fetcher:
  concurrency: 5
  delay_between_requests: 0.5
  timeout: 30
  retry_count: 3

reports:
  github_pages_url: "https://<username>.github.io/claude-code-doc-monitor"
```

**Environment Variables:**
- `TELEGRAM_BOT_TOKEN` - Bot token from @BotFather
- `TELEGRAM_CHAT_ID` - Your Telegram chat ID

---

## Module Details

### src/fetcher.py

```python
import httpx
import asyncio
from dataclasses import dataclass
from typing import Optional

@dataclass
class FetchResult:
    page_slug: str
    content: Optional[str]
    status_code: int
    error: Optional[str] = None

class DocumentFetcher:
    def __init__(self, base_url: str, language: str = "en"):
        self.base_url = base_url
        self.language = language
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    def get_markdown_url(self, page_slug: str) -> str:
        return f"{self.base_url}/{self.language}/{page_slug}.md"

    async def fetch_page(self, page_slug: str) -> FetchResult:
        url = self.get_markdown_url(page_slug)
        try:
            response = await self.client.get(url)
            if response.status_code == 200:
                return FetchResult(page_slug, response.text, 200)
            return FetchResult(page_slug, None, response.status_code, f"HTTP {response.status_code}")
        except Exception as e:
            return FetchResult(page_slug, None, 0, str(e))

    async def fetch_all(self, pages: list[str], concurrency: int = 5) -> list[FetchResult]:
        semaphore = asyncio.Semaphore(concurrency)
        async def fetch_with_limit(page: str) -> FetchResult:
            async with semaphore:
                result = await self.fetch_page(page)
                await asyncio.sleep(0.5)  # Rate limiting
                return result
        return await asyncio.gather(*[fetch_with_limit(p) for p in pages])
```

### src/differ.py

```python
import difflib
from dataclasses import dataclass
from diff_match_patch import diff_match_patch

@dataclass
class DiffResult:
    page_slug: str
    has_changes: bool
    old_content: str
    new_content: str
    unified_diff: str
    html_diff: str
    added_lines: int
    removed_lines: int
    summary: str

class DocumentDiffer:
    def __init__(self):
        self.dmp = diff_match_patch()

    def compute_diff(self, page_slug: str, old_content: str, new_content: str) -> DiffResult:
        has_changes = old_content != new_content
        if not has_changes:
            return DiffResult(page_slug, False, old_content, new_content, "", "", 0, 0, "No changes")

        # Generate unified diff
        unified = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{page_slug}.md",
            tofile=f"b/{page_slug}.md"
        ))

        # Generate HTML diff
        diffs = self.dmp.diff_main(old_content, new_content)
        self.dmp.diff_cleanupSemantic(diffs)
        html_diff = self.dmp.diff_prettyHtml(diffs)

        # Count changes
        old_lines = set(old_content.splitlines())
        new_lines = set(new_content.splitlines())
        added = len(new_lines - old_lines)
        removed = len(old_lines - new_lines)

        summary = f"+{added} lines, -{removed} lines" if added or removed else "Formatting changes"

        return DiffResult(page_slug, True, old_content, new_content,
                         "".join(unified), html_diff, added, removed, summary)
```

### src/notifier.py

```python
from telegram import Bot
from telegram.constants import ParseMode

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_notification(self, title: str, summary: str,
                                 changed_pages: list[dict], report_url: str) -> bool:
        message = f"<b>{title}</b>\n\n{summary}\n\n<b>Changed Pages:</b>\n"

        for page in changed_pages[:10]:
            message += f"- <a href='{page['url']}'>{page['page']}</a>: {page['summary']}\n"

        if len(changed_pages) > 10:
            message += f"... and {len(changed_pages) - 10} more\n"

        message += f"\n<a href='{report_url}'>View Full Diff Report</a>"

        await self.bot.send_message(
            chat_id=self.chat_id,
            text=message[:4096],
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return True
```

---

## Pages to Monitor (from llms.txt)

```yaml
# config/pages.yaml
pages:
  - amazon-bedrock
  - analytics
  - changelog
  - checkpointing
  - chrome
  - claude-code-on-the-web
  - cli-reference
  - common-workflows
  - costs
  - data-usage
  - desktop
  - devcontainer
  - discover-plugins
  - github-actions
  - gitlab-ci-cd
  - google-vertex-ai
  - headless
  - hooks
  - hooks-guide
  - iam
  - interactive-mode
  - jetbrains
  - legal-and-compliance
  - llm-gateway
  - mcp
  - memory
  - microsoft-foundry
  - model-config
  - monitoring-usage
  - network-config
  - output-styles
  - overview
  - plugin-marketplaces
  - plugins
  - plugins-reference
  - quickstart
  - sandboxing
  - security
  - settings
  - setup
  - skills
  - slack
  - slash-commands
  - statusline
  - sub-agents
  - terminal-config
  - third-party-integrations
  - troubleshooting
  - vs-code
```

---

## Telegram Bot Setup Instructions

### Step 1: Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Start a conversation and send `/newbot`
3. Follow the prompts:
   - Enter a display name (e.g., "Claude Code Doc Monitor")
   - Enter a username ending in `bot` (e.g., `claude_docs_monitor_bot`)
4. BotFather will provide your **API Token** - save it securely

### Step 2: Get Your Chat ID

1. Start a conversation with your new bot in Telegram
2. Send any message (e.g., `/start`)
3. Open this URL in your browser (replace `<TOKEN>` with your bot token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. Find `"chat":{"id":XXXXXXXX}` in the response - that's your Chat ID

### Step 3: Configure GitHub Secrets

1. Go to your repository Settings > Secrets and variables > Actions
2. Add these secrets:
   - `TELEGRAM_BOT_TOKEN`: Your bot token
   - `TELEGRAM_CHAT_ID`: Your chat ID

---

## Notes

- The `llms.txt` file at `https://code.claude.com/docs/llms.txt` provides the authoritative list of pages
- Each page can be fetched as markdown by appending `.md` to the URL
- Git history provides unlimited version retention
- GitHub Pages serves the diff reports publicly
- Cron runs daily at 6 AM UTC (configurable)

---

## Local Development

```bash
# Clone and setup
cd /Users/nemo/Projects/vibe_ideas/claude-code-doc-monitor
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your Telegram credentials

# Run manually
python -m src.main

# Run with verbose logging
python -m src.main --verbose
```

---

## macOS Cron Alternative (launchd)

Create `~/Library/LaunchAgents/com.user.claudecodemonitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.claudecodemonitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>src.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/nemo/Projects/vibe_ideas/claude-code-doc-monitor</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/doc-monitor.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/doc-monitor.err</string>
</dict>
</plist>
```

Load with:
```bash
launchctl load ~/Library/LaunchAgents/com.user.claudecodemonitor.plist
```

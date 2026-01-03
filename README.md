# Claude Code Documentation Monitor

Monitor Claude Code documentation for updates with Telegram notifications and GitHub Pages diff reports.

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and set your Telegram credentials.

## Usage

```bash
python -m src.main
```

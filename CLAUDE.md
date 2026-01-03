# CLAUDE.md

## Code Style

- **Concise over verbose**: No unnecessary comments, docstrings only for public APIs
- **Type hints**: Always use them, leverage `typing` and `Annotated` where useful
- **Imports**: Use absolute imports, group as stdlib → third-party → local
- **Naming**: snake_case for functions/vars, PascalCase for classes, UPPER_CASE for constants

## Testing Requirements

- **Write tests first** or immediately after implementation—never skip
- Use `pytest` as the test runner
- Prefer small, focused test functions over large test classes
- Use `pytest.mark.parametrize` for input variations
- Mock external services (APIs, DBs) — use `pytest-mock` or `unittest.mock`
- **Run tests before declaring any task complete**: `pytest -xvs`

## Before Committing

Run this sequence:

```bash
ruff check --fix .    # lint + autofix
ruff format .         # format
pytest -xvs           # test (stop on first failure)
```

## Project Patterns

### LLM/ML Projects

- Keep training configs in YAML/TOML, not hardcoded
- Separate data loading, model definition, and training loops
- Use `pathlib.Path` for all file operations
- Prefer `datasets` (HuggingFace) for data pipelines
- Log experiments with simple abstractions (wandb, mlflow, or even just JSON logs)

### Scraping/Crawling

- Use `httpx` (async) or `requests` (sync) — prefer async for crawlers
- Always set reasonable timeouts and retries
- Respect `robots.txt` and rate limits
- Use `selectolux` or `parsel` over `BeautifulSoup` for speed
- Structure: fetcher → parser → storage (keep them decoupled)

### Web Services

- FastAPI for APIs, keep routes thin—logic in services/utils
- Pydantic models for all request/response schemas
- Use dependency injection for DB sessions, configs
- Return proper HTTP status codes

### Frontend

- Keep JS/TS minimal and typed
- Prefer htmx + Jinja for simple UIs over heavy frameworks

## Workflow Rules

1. **Ask clarifying questions** if requirements are ambiguous
2. **Small incremental changes** — commit logical units, not everything at once
3. **Don't over-engineer** — YAGNI (You Aren't Gonna Need It)
4. **If debugging > 2 attempts**, step back and add logging/tests first
5. **Read existing code style** before adding new files—match conventions

## Common Commands

```bash
# virtual env
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# quick test single file
pytest tests/test_foo.py -xvs

# type check (if using)
pyright .

# see test coverage
pytest --cov=src --cov-report=term-missing
```

## Don'ts

- Don't add `print()` for debugging—use `logging` or proper debugger
- Don't catch bare `except:` — be specific
- Don't leave TODOs without context
- Don't write "wrapper" classes that add no value
- Don't repeat yourself—if copying code, extract a function

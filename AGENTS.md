# Repository Guidelines

Personal cognitive-profile system that collects behavior data (Bilibili, browser history, GitHub, RSS), builds an interest profile, and serves a React SPA + FastAPI dashboard.

## Project Structure & Module Organization

- `core/` — data models, SQLite access, plugin manager
- `plugins/<source>/plugin.py` — data source plugins (must subclass `DataSourcePlugin`)
- `analysis/` — keyword extraction, topic clustering, trends, insights
- `report/` — report generator and HTML templates
- `web/` — React SPA (Vite + TypeScript), API client under `web/src/api/`
- `api/` — FastAPI service layer (routers under `api/routers/`, background tasks in `api/tasks.py`)
- `scripts/` — CLI tools: `init_db.py`, `sync.py`, `generate_report.py`, `migrate.py`
- `tests/` — plain-script tests (no pytest dependency)
- `data/` — runtime SQLite database and generated reports (gitignored)

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt        # install dependencies
python scripts/init_db.py              # create database schema
python scripts/sync.py --source bilibili  # pull data from a source
python scripts/generate_report.py --period weekly  # generate a report
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8501  # SPA + API 同源
make test                              # run offline backend tests
make test-api                          # run API tests (outside sandboxed shells)
make test-web                          # run React SPA tests
docker compose up app                  # run the app in Docker
```

## Coding Style & Naming Conventions

- Python 3.11+, PEP 8, 4-space indentation; docstrings and comments in Chinese (project convention).
- `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- Plugins implement `name`, `display_name`, `version`, `setup()`, `test_connection()`, `fetch()` from `core.plugin_loader.DataSourcePlugin`.
- No linter or formatter is configured; keep diffs small and imports organized.

## Testing Guidelines

- Run tests directly: `python tests/test_basic.py` and `python tests/test_models.py`.
- `tests/test_analysis.py`, `tests/test_plugins.py`, `tests/test_api.py` are pytest-compatible; run `python tests/test_api.py` outside sandboxed shells (asyncio threadpools are blocked inside them).
- `tests/test_graph.py` covers the precomputed interest graph used by `GET /api/v1/graph`.
- `tests/test_database.py` covers SQLite/PostgreSQL dual-backend and background-task persistence.
- Name test files `test_*.py` and functions `test_*()`.
- Tests must be offline: use in-memory databases and sample data, never real cookies or live APIs.

## Commit & Pull Request Guidelines

- The `.git` path is an environment-managed read-only mount, so Git metadata lives in `.git-data/`. Use:
  `git --git-dir=$PWD/.git-data add . && git --git-dir=$PWD/.git-data commit -m "..."`.
- Follow Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`.
- PRs: describe what changed and why, link the related issue, confirm `python main.py`, sync, and report generation still run, and include screenshots for UI changes.
- Never include `.env` contents, cookies, or tokens in commits or PRs.

## Security & Configuration

- Secrets live in `.env` (gitignored); `config.yaml` references them as `${VAR}` and never stores real values.
- Accounts use scrypt-hashed passwords (login/register via `api/routers/auth.py`, API Bearer tokens); per-user source credentials are encrypted with `APP_SECRET_KEY`; `APP_PASSWORD` is no longer used.
- Enable/disable sources and tune analysis via `config.yaml`; database URL defaults to `sqlite:///./data/profile.db`.
- `DATABASE_URL` (or `database.url` in `config.yaml`) selects the backend: `sqlite:///...` or `postgresql+psycopg://...`; run `python scripts/migrate_db.py --from-url ... --to-url ...` to copy data across backends.
- Redact cookies/tokens when showing config in the settings page (`web/src/pages/SettingsPage.tsx`).

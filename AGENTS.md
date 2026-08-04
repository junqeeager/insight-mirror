# Repository Guidelines

Personal cognitive-profile system that collects behavior data (Bilibili, browser history, GitHub, RSS), builds an interest profile, and serves a Streamlit dashboard.

## Project Structure & Module Organization

- `core/` — data models, SQLite access, plugin manager
- `plugins/<source>/plugin.py` — data source plugins (must subclass `DataSourcePlugin`)
- `analysis/` — keyword extraction, topic clustering, trends, insights
- `report/` — report generator and HTML templates
- `frontend/` — Streamlit app entry (`app.py`) and pages under `frontend/pages/`
- `scripts/` — CLI tools: `init_db.py`, `sync.py`, `generate_report.py`
- `tests/` — plain-script tests (no pytest dependency)
- `data/` — runtime SQLite database and generated reports (gitignored)

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt        # install dependencies
python scripts/init_db.py              # create database schema
python scripts/sync.py --source bilibili  # pull data from a source
python scripts/generate_report.py --period weekly  # generate a report
streamlit run frontend/app.py          # start dashboard on :8501
docker compose up app                  # run the app in Docker
```

## Coding Style & Naming Conventions

- Python 3.11+, PEP 8, 4-space indentation; docstrings and comments in Chinese (project convention).
- `snake_case` modules/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- Plugins implement `name`, `display_name`, `version`, `setup()`, `test_connection()`, `fetch()` from `core.plugin_loader.DataSourcePlugin`.
- No linter or formatter is configured; keep diffs small and imports organized.

## Testing Guidelines

- Run tests directly: `python tests/test_basic.py` and `python tests/test_models.py`.
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
- Enable/disable sources and tune analysis via `config.yaml`; database URL defaults to `sqlite:///./data/profile.db`.
- Redact cookies/tokens when showing config in the frontend settings page.

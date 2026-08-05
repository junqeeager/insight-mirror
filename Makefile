PYTHON ?= python3

.PHONY: test test-api run-api run-web run-web-dev build-web test-web sync init-db

test:
	$(PYTHON) tests/test_frontend_theme.py
	$(PYTHON) tests/test_frontend_auth.py
	$(PYTHON) tests/test_database.py
	$(PYTHON) tests/test_analysis.py
	$(PYTHON) tests/test_plugins.py
	$(PYTHON) tests/test_secret_guard.py
	$(PYTHON) tests/test_multiuser.py

test-api:
	$(PYTHON) tests/test_api.py

init-db:
	$(PYTHON) scripts/init_db.py

sync:
	$(PYTHON) scripts/sync.py

run-api:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8502

run-web:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8501

run-web-dev:
	cd web && npm run dev

build-web:
	npm --prefix web run build

test-web:
	npm --prefix web run test

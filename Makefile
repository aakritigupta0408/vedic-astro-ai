.PHONY: install test test-cov lint fmt typecheck clean ingest-rules ingest-cases build-index

# ─────────────────────────────────────────────────────────────────────────────
# Development
# ─────────────────────────────────────────────────────────────────────────────

install:
	uv sync --extra dev

test:
	uv run pytest tests/ -v

test-engines:
	uv run pytest tests/engines/ -v

# Run only fast (non-integration) tests — no ephemeris required
test-fast:
	uv run pytest tests/ -v -m "not integration"

test-cov:
	uv run pytest tests/ --cov=src/vedic_astro --cov-report=html --cov-report=term-missing

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/vedic_astro/engines/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete; \
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage

# ─────────────────────────────────────────────────────────────────────────────
# Offline pipelines (run once, idempotent)
# ─────────────────────────────────────────────────────────────────────────────

ingest-rules:
	uv run python scripts/extract_rules.py

ingest-cases:
	uv run python scripts/ingest_vedastro.py

build-index:
	uv run python scripts/build_index.py

# ─────────────────────────────────────────────────────────────────────────────
# Services
# ─────────────────────────────────────────────────────────────────────────────

serve-api:
	uv run uvicorn vedic_astro.api:app --reload --host 0.0.0.0 --port 8000

serve-ui:
	uv run python ui/app.py

up:
	docker compose up -d

down:
	docker compose down

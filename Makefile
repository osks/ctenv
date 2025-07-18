.PHONY: dev
dev:
	@echo "Setting up development environment with uv..."
	@test -d .venv || uv venv
	@uv pip install -e '.[test]'
	@echo "✓ Development environment ready"
	@echo "  Activate with: source .venv/bin/activate"

.PHONY: test
test: dev
	@echo "Running tests..."
	@uv run pytest tests/ -v

.PHONY: test-unit
test-unit: dev
	@echo "Running unit tests only..."
	@uv run pytest tests/ -v -m unit

.PHONY: test-integration
test-integration: dev
	@echo "Running integration tests..."
	@uv run pytest tests/ -v -m integration

.PHONY: test-cov
test-cov: dev
	@echo "Running tests with coverage..."
	@uv run pytest tests/ -v --cov=ctenv --cov-report=term-missing

.PHONY: test-all
test-all: dev
	@echo "Running tests on multiple Python versions with tox..."
	@uv run tox

.PHONY: lint
lint: dev
	@echo "Checking code style..."
	@uv run ruff check ctenv.py tests/

.PHONY: lint-fix
lint-fix: dev
	@echo "Fixing code style..."
	@uv run ruff check --fix ctenv.py tests/

.PHONY: format
format: dev
	@echo "Formatting code..."
	@uv run ruff format ctenv.py tests/

.PHONY: clean
clean:
	@echo "Cleaning up..."
	@rm -rf .venv/
	@rm -rf .pytest_cache/
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete
	@find . -name "*.pyo" -delete
	@find . -name "*~" -delete
	@echo "✓ Cleaned up"

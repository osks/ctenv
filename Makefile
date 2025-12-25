MAKEFILE_ABS_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

.DEFAULT_GOAL := help

##@ Help
.PHONY: help
help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


.PHONY: all
all: lint typecheck test-all


##@ Environment
.PHONY: dev
dev: ## Setup development environment
	@echo "Setting up development environment with uv..."
	@test -d .venv || uv venv
	@uv pip install -e '.[test]'
	@echo "✓ Development environment ready"
	@echo "  Activate with: source .venv/bin/activate"


.PHONY: clean
clean: ## Clean up build artifacts
	@echo "Cleaning up..."
	@rm -rf dist
	@rm -rf ctenv.egg-info
	@rm -rf .venv/
	@rm -rf .pytest_cache/
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete
	@find . -name "*.pyo" -delete
	@find . -name "*~" -delete
	@echo "✓ Cleaned up"


##@ Compiling

.PHONY: build
build: ## Build
	@echo "Building..."
	@uv build


##@ Tests

.PHONY: test
test: dev ## Run tests
	@echo "Running tests..."
	@uv run pytest tests/ -v

.PHONY: test-unit
test-unit: dev ## Run unit tests only
	@echo "Running unit tests only..."
	@uv run pytest tests/ -v -m unit

.PHONY: test-integration
test-integration: dev ## Run integration tests only
	@echo "Running integration tests..."
	@uv run pytest tests/ -v -m integration

.PHONY: test-cov
test-cov: dev ## Run tests with coverage
	@echo "Running tests with coverage..."
	@uv run pytest tests/ -v --cov=ctenv --cov-report=term-missing

.PHONY: test-all
test-all: dev ## Run tests with multiple Python versions
	@echo "Running tests on multiple Python versions with tox..."
	@uv run tox


##@ Linting / Formatting

.PHONY: lint
lint: dev ## Check code style
	@echo "Checking code style..."
	@uv run ruff check ctenv/ tests/
	@echo "Running type checking..."
	@uv run mypy ctenv/ tests/

.PHONY: lint-fix
lint-fix: dev ## Fix code style issues automatically
	@echo "Fixing code style..."
	@uv run ruff check --fix ctenv/ tests/

.PHONY: typecheck
typecheck: dev
	@echo "Running type checking..."
	@uv run mypy ctenv/ tests/

.PHONY: format
format: dev ## Format code
	@echo "Formatting code..."
	@uv run ruff format ctenv/ tests/

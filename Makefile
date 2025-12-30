MAKEFILE_ABS_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

.DEFAULT_GOAL := help

##@ Help
.PHONY: help
help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


.PHONY: all
all: lint typecheck test-py-versions


##@ Environment
.PHONY: dev
dev: ## Setup development environment
	@uv sync --all-extras


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
test: dev ## Run unit tests
	@uv run pytest tests/ -v

.PHONY: test-all
test-all: test test-e2e test-py-versions ## Run all tests

.PHONY: test-e2e
test-e2e: lima-setup ## Run e2e tests (in Lima VM)
	@./scripts/lima.sh run make test-e2e-python-no-vm test-e2e-bats-no-vm
	@./scripts/lima.sh down

# Run e2e tests (on host, requires Docker)
.PHONY: test-e2e-no-vm
test-e2e-no-vm:
	@bats tests-e2e/bats/
	@uv run pytest tests-e2e/python/ -v

# Run e2e Python tests (on host, requires Docker)
.PHONY: test-e2e-python-no-vm
test-e2e-python-no-vm:
	@uv run pytest tests-e2e/python/ -v

# Run e2e BATS tests (on host, requires Docker)
.PHONY: test-e2e-bats-no-vm
test-e2e-bats-no-vm:
	@bats tests-e2e/bats/

.PHONY: lima-setup
lima-setup: ## Setup Lima VM (for e2e tests)
	@./scripts/lima.sh setup

.PHONY: lima-down
lima-down: ## Teardown Lima VM (for e2e tests)
	@./scripts/lima.sh down

.PHONY: test-cov
test-cov: dev ## Run unit tests with coverage
	@uv run pytest tests/ -v --cov=ctenv --cov-report=term-missing

.PHONY: test-py-versions
test-py-versions: dev ## Run tests with multiple Python versions
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

# E2E Tests

End-to-end tests run in an isolated Lima VM with Docker available.

## Structure

```
tests-e2e/
├── bats/      # BATS shell tests
└── python/    # pytest Python tests
```

## Requirements

- [Lima](https://lima-vm.io/) (`brew install lima`)
- [BATS](https://github.com/bats-core/bats-core) (`brew install bats-core`)

## Running Tests

```bash
# Run all e2e tests (uses Lima VM)
make test-e2e

# Run locally (requires Docker on host)
make test-e2e-no-vm
```

## Lima Commands

```bash
./scripts/lima.sh setup    # create/start VM
./scripts/lima.sh status   # show VM status
./scripts/lima.sh sync     # sync files + deps
./scripts/lima.sh down     # stop/delete VM
```

## Running Specific Tests

```bash
# BATS tests in Lima
./scripts/lima.sh run bats tests-e2e/bats/

# pytest tests in Lima
./scripts/lima.sh run uv run pytest tests-e2e/python/ -v

# Locally (requires Docker)
bats tests-e2e/bats/
uv run pytest tests-e2e/python/ -v
```

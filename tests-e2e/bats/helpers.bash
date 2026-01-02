# Shared helpers for BATS tests

# Determine project root from test file location
BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"

# Use project's ctenv, not global tool
CTENV="uv run --project $PROJECT_ROOT python -m ctenv"

# -----------------------------------------------------------------------------
# Runtime parameterization helpers
# -----------------------------------------------------------------------------

# Runtimes to test
RUNTIMES=(docker podman)

# Skip if runtime not available
_require_runtime() {
    command -v "$RUNTIME" >/dev/null || skip "$RUNTIME not available"
}

# Register a test function for all runtimes
# Usage: register_runtime_test _test_func_name "test description"
register_runtime_test() {
    local name="$1"
    local description="$2"

    for runtime in "${RUNTIMES[@]}"; do
        eval "${name}_${runtime}() { RUNTIME=$runtime; ${name}; }"
        bats_test_function \
            --description "[$runtime] $description" \
            -- "${name}_${runtime}"
    done
}

# Test fixtures
FIXTURES_DIR="$PROJECT_ROOT/tests-e2e/fixtures"
PROJECT1="$FIXTURES_DIR/project1"

# Generate unique container name for tests
container_name() {
    local suffix="${1:-test}"
    echo "ctenv-test-${suffix}-$$"
}

# Strip carriage returns from output (Docker on macOS adds \r)
trim_cr() {
    echo "${1//$'\r'/}"
}

# Assert output equals expected value (after trimming \r)
assert_output() {
    local expected="$1"
    local actual="${output//$'\r'/}"
    if [[ "$actual" != "$expected" ]]; then
        echo "expected: '$expected'"
        echo "actual:   '$actual'"
        return 1
    fi
}

# Assert last line of output equals expected (handles Docker pull noise)
assert_last_line() {
    local expected="$1"
    local actual="${output//$'\r'/}"
    local last_line="${actual##*$'\n'}"
    if [[ "$last_line" != "$expected" ]]; then
        echo "expected last line: '$expected'"
        echo "actual last line:   '$last_line'"
        return 1
    fi
}

# Mount assertion helpers (take full docker inspect JSON output)
assert_mount_rw() {
    local inspect="$1" dest="$2"
    local rw=$(echo "$inspect" | jq -r ".[0].Mounts[] | select(.Destination == \"$dest\") | .RW")
    [ "$rw" = "true" ] || { echo "Expected $dest to be read-write, got RW=$rw"; return 1; }
}

assert_mount_ro() {
    local inspect="$1" dest="$2"
    local rw=$(echo "$inspect" | jq -r ".[0].Mounts[] | select(.Destination == \"$dest\") | .RW")
    [ "$rw" = "false" ] || { echo "Expected $dest to be read-only, got RW=$rw"; return 1; }
}

assert_mount_exists() {
    local inspect="$1" dest="$2"
    echo "$inspect" | jq -e ".[0].Mounts[] | select(.Destination == \"$dest\")" >/dev/null \
        || { echo "Expected mount at $dest to exist"; return 1; }
}

assert_mount_not_exists() {
    local inspect="$1" dest="$2"
    echo "$inspect" | jq -e ".[0].Mounts[] | select(.Destination == \"$dest\")" >/dev/null \
        && { echo "Expected no mount at $dest"; return 1; } || true
}

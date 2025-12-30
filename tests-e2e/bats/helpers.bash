# Shared helpers for BATS tests

# Determine project root from test file location
BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"

# Use project's ctenv, not global tool
CTENV="uv run --project $PROJECT_ROOT python -m ctenv"

# Test fixtures
FIXTURES_DIR="$PROJECT_ROOT/tests-e2e/fixtures"
PROJECT1="$FIXTURES_DIR/project1"

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

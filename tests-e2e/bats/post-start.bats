#!/usr/bin/env bats

# Tests for post-start commands
# Commands that run as root before dropping to user and executing user command

load helpers

setup() {
    TEMP_WORKSPACE=$(mktemp -d)
}

teardown() {
    rm -rf "$TEMP_WORKSPACE"
}

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_post_start_executes() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "marker" > /tmp/post_start_marker' \
        -- cat /tmp/post_start_marker
    [ "$status" -eq 0 ]
    [[ "$output" == *"marker"* ]]
}
register_runtime_test _test_post_start_executes "post-start: command executes before user command"

_test_post_start_runs_as_root() {
    _require_runtime
    # Post-start commands run as root, so they can modify /etc
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "test" > /etc/post_start_test' \
        -- cat /etc/post_start_test
    [ "$status" -eq 0 ]
    [[ "$output" == *"test"* ]]
}
register_runtime_test _test_post_start_runs_as_root "post-start: command runs as root (can write to /etc)"

_test_post_start_order() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo first > /tmp/order' \
        --post-start-command 'echo second >> /tmp/order' \
        --post-start-command 'echo third >> /tmp/order' \
        -- cat /tmp/order
    [ "$status" -eq 0 ]
    # Verify order: first must appear before second, second before third
    trimmed=$(trim_cr "$output")
    # Check all three are present
    [[ "$trimmed" == *"first"* ]]
    [[ "$trimmed" == *"second"* ]]
    [[ "$trimmed" == *"third"* ]]
    # Check order using pattern: first.*second.*third (with newlines)
    [[ "$trimmed" =~ first.*second.*third ]]
}
register_runtime_test _test_post_start_order "post-start: multiple commands execute in order"

_test_post_start_writes_workspace() {
    _require_runtime
    # Post-start runs inside container, so use workdir (which is the mounted workspace)
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "from-post-start" > post_start_file.txt' \
        -- cat post_start_file.txt
    [ "$status" -eq 0 ]
    [[ "$output" == *"from-post-start"* ]]
}
register_runtime_test _test_post_start_writes_workspace "post-start: can write to mounted workspace"

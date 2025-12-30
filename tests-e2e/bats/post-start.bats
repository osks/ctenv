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

@test "post-start: command executes before user command" {
    run $CTENV --quiet run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "marker" > /tmp/post_start_marker' \
        -- cat /tmp/post_start_marker
    [ "$status" -eq 0 ]
    [[ "$output" == *"marker"* ]]
}

@test "post-start: command runs as root (can write to /etc)" {
    # Post-start commands run as root, so they can modify /etc
    run $CTENV --quiet run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "test" > /etc/post_start_test' \
        -- cat /etc/post_start_test
    [ "$status" -eq 0 ]
    [[ "$output" == *"test"* ]]
}

@test "post-start: multiple commands execute in order" {
    run $CTENV --quiet run --project-dir "$TEMP_WORKSPACE" \
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

@test "post-start: can write to mounted workspace" {
    # Post-start runs inside container, so use workdir (which is the mounted workspace)
    run $CTENV --quiet run --project-dir "$TEMP_WORKSPACE" \
        --post-start-command 'echo "from-post-start" > post_start_file.txt' \
        -- cat post_start_file.txt
    [ "$status" -eq 0 ]
    [[ "$output" == *"from-post-start"* ]]
}

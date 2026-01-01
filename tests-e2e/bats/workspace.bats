#!/usr/bin/env bats

# Tests for workspace behavior
# Reference: Workspace (-w / --workspace)

load helpers

@test "workspace: defaults to project directory" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}

@test "workspace: subdirectory mounted under project mount" {
    # Example: -w ./src → /project/src mounted at /repo/src
    cd "$PROJECT1"
    run $CTENV --quiet run --workspace ./src test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo/src"
}

@test "workspace: workdir follows workspace not project" {
    cd "$PROJECT1"
    run $CTENV --quiet run --workspace ./src test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo/src"
}

@test "workspace: workspace files are accessible" {
    cd "$PROJECT1"
    run $CTENV --quiet run --workspace ./src test -- ls /repo/src
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}

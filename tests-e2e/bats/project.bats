#!/usr/bin/env bats

# Tests for project directory and project mount behavior
# Reference: Project (-p / --project)

load helpers

@test "project: auto-detected from .ctenv.toml location" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}

@test "project: project_mount from config applied" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}

@test "project: --project-mount sets mount path" {
    cd "$PROJECT1"
    run $CTENV --quiet run --project-mount /myproject test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/myproject"
}

@test "project: --project-dir sets project dir" {
    run $CTENV --quiet run --project-dir "$PROJECT1" test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}

@test "project: --project-dir and --project-mount together" {
    run $CTENV --quiet run --project-dir "$PROJECT1" --project-mount /custom test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/custom"
}

@test "project: --project-mount supports mount options" {
    cd "$PROJECT1"
    run $CTENV --quiet run --project-mount /repo:ro test -- cat /proc/mounts
    [ "$status" -eq 0 ]
    # Check that /repo mount has 'ro' option
    [[ "$output" == *"/repo"*"ro"* ]]
}

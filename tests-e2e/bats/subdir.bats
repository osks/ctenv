#!/usr/bin/env bats

# Tests for subdir behavior
# Reference: Subdir (-s / --subdir)

load helpers

@test "subdir: defaults to project directory when not specified" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- ls /repo
    [ "$status" -eq 0 ]
    [[ "$output" == *"README.md"* ]]
    [[ "$output" == *"src"* ]]
}

@test "subdir: single subdir limits mount" {
    cd "$PROJECT1"
    run $CTENV --quiet run --subdir ./src test -- ls /repo/src
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}

@test "subdir: project root not accessible when subdir specified" {
    cd "$PROJECT1"
    run $CTENV --quiet run --subdir ./src test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}

@test "subdir: multiple subdirs both accessible" {
    cd "$PROJECT1"
    run $CTENV --quiet run -s ./src -s ./scripts test -- sh -c "ls /repo/src && ls /repo/scripts"
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
    [[ "$output" == *"build.sh"* ]]
}

@test "subdir: project root not accessible with multiple subdirs" {
    cd "$PROJECT1"
    run $CTENV --quiet run -s ./src -s ./scripts test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}

@test "subdir: read-only option respected" {
    cd "$PROJECT1"
    # Try to create a file in read-only subdir - should fail
    run $CTENV --quiet run -s ./scripts::ro test -- touch /repo/scripts/newfile.txt
    [ "$status" -ne 0 ]
}

@test "subdir: mixed read-write and read-only" {
    cd "$PROJECT1"
    # src is rw, scripts is ro
    run $CTENV --quiet run -s ./src -s ./scripts::ro test -- sh -c "touch /repo/src/testfile.txt && rm /repo/src/testfile.txt"
    [ "$status" -eq 0 ]
}

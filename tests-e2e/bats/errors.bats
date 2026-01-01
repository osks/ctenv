#!/usr/bin/env bats

# Tests for error handling
# Verify ctenv provides useful errors for common mistakes

load helpers

@test "error: unknown container name" {
    cd "$PROJECT1"
    run $CTENV run nonexistent_container -- echo hello
    [ "$status" -ne 0 ]
    [[ "$output" == *"Unknown container"* ]] || [[ "$stderr" == *"Unknown container"* ]]
}

@test "error: invalid subcommand" {
    run $CTENV invalidcommand
    [ "$status" -eq 2 ]  # argparse returns 2 for invalid choices
}

@test "error: subpath does not exist" {
    cd "$PROJECT1"
    run $CTENV run --subpath ./nonexistent_dir test -- pwd
    [ "$status" -ne 0 ]
    [[ "$output" == *"does not exist"* ]] || [[ "$stderr" == *"does not exist"* ]]
}

@test "error: build-arg without equals sign" {
    cd "$PROJECT1"
    run $CTENV run --build-arg INVALID_NO_EQUALS --dry-run -- echo hello
    [ "$status" -eq 1 ]
    [[ "$output" == *"Invalid build argument"* ]] || [[ "$stderr" == *"Invalid build argument"* ]]
}

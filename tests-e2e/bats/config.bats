#!/usr/bin/env bats

# Tests for config command
# Introspection of effective configuration

load helpers

setup() {
    TEMP_WORKSPACE=$(mktemp -d)
}

teardown() {
    rm -rf "$TEMP_WORKSPACE"
}

@test "config: shows default image" {
    cd "$TEMP_WORKSPACE"
    run $CTENV config
    [ "$status" -eq 0 ]
    [[ "$output" == *"ubuntu"* ]]
}

@test "config: shows default command" {
    cd "$TEMP_WORKSPACE"
    run $CTENV config
    [ "$status" -eq 0 ]
    [[ "$output" == *"bash"* ]]
}

@test "config: shows containers from project config" {
    cd "$PROJECT1"
    run $CTENV config
    [ "$status" -eq 0 ]
    # Fixture has 'test' and 'alpine' containers
    [[ "$output" == *"test"* ]]
    [[ "$output" == *"alpine"* ]]
}

@test "config: config show is alias for config" {
    cd "$PROJECT1"
    run $CTENV config show
    [ "$status" -eq 0 ]
    [[ "$output" == *"test"* ]]
}

@test "config: shows image from project config" {
    cd "$PROJECT1"
    run $CTENV config
    [ "$status" -eq 0 ]
    # Fixture has ubuntu:22.04 for test container
    [[ "$output" == *"ubuntu:22.04"* ]]
}

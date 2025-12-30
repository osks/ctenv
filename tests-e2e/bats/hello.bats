#!/usr/bin/env bats

# Simple hello world BATS test example

@test "hello world - basic assertion" {
    result="hello"
    [ "$result" = "hello" ]
}

@test "hello world - command output" {
    run echo "Hello, BATS!"
    [ "$status" -eq 0 ]
    [ "$output" = "Hello, BATS!" ]
}

@test "ctenv --help shows usage" {
    run uv run ctenv --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"usage"* ]] || [[ "$output" == *"Usage"* ]]
}

@test "ctenv --version works" {
    run uv run ctenv --version
    [ "$status" -eq 0 ]
}

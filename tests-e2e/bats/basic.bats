#!/usr/bin/env bats

load helpers

@test "ctenv --help shows usage" {
    run $CTENV --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"run"* ]]
}

@test "ctenv --version works" {
    run $CTENV --version
    [ "$status" -eq 0 ]
}

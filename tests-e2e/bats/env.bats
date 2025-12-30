#!/usr/bin/env bats

# Tests for environment variable passing
# Reference: Environment (-e / --env)

load helpers

@test "env: --env passes variable to container" {
    cd "$PROJECT1"
    run $CTENV --quiet run --env TEST_VAR=hello test -- sh -c 'echo $TEST_VAR'
    [ "$status" -eq 0 ]
    assert_last_line "hello"
}

@test "env: --env passes host variable to container" {
    cd "$PROJECT1"
    TEST_FROM_HOST=world run $CTENV --quiet run --env TEST_FROM_HOST test -- sh -c 'echo $TEST_FROM_HOST'
    [ "$status" -eq 0 ]
    assert_last_line "world"
}

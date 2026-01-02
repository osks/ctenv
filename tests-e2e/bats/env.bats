#!/usr/bin/env bats

# Tests for environment variable passing
# Reference: Environment (-e / --env)

load helpers

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_env_value() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --env TEST_VAR=hello test -- sh -c 'echo $TEST_VAR'
    [ "$status" -eq 0 ]
    assert_last_line "hello"
}
register_runtime_test _test_env_value "env: --env passes variable to container"

_test_env_host() {
    _require_runtime
    cd "$PROJECT1"
    TEST_FROM_HOST=world run $CTENV --quiet --runtime "$RUNTIME" run --env TEST_FROM_HOST test -- sh -c 'echo $TEST_FROM_HOST'
    [ "$status" -eq 0 ]
    assert_last_line "world"
}
register_runtime_test _test_env_host "env: --env passes host variable to container"

_test_env_multiple() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --env VAR1=one --env VAR2=two test -- sh -c 'echo $VAR1-$VAR2'
    [ "$status" -eq 0 ]
    assert_last_line "one-two"
}
register_runtime_test _test_env_multiple "env: multiple environment variables"

#!/usr/bin/env bats

# Tests for user identity preservation - the core ctenv value proposition
# ctenv creates a user inside containers with matching UID/GID to avoid permission issues

load helpers

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_user_uid() {
    _require_runtime
    cd "$PROJECT1"
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" run test -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}
register_runtime_test _test_user_uid "user identity: container user has same UID as host"

_test_user_gid() {
    _require_runtime
    cd "$PROJECT1"
    host_gid=$(id -g)
    run $CTENV --quiet --runtime "$RUNTIME" run test -- id -g
    [ "$status" -eq 0 ]
    assert_last_line "$host_gid"
}
register_runtime_test _test_user_gid "user identity: container user has same GID as host"

_test_user_name() {
    _require_runtime
    cd "$PROJECT1"
    host_user=$(whoami)
    run $CTENV --quiet --runtime "$RUNTIME" run test -- whoami
    [ "$status" -eq 0 ]
    assert_last_line "$host_user"
}
register_runtime_test _test_user_name "user identity: container username matches host"

_test_user_home() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- sh -c 'echo $HOME'
    [ "$status" -eq 0 ]
    # HOME should be non-empty and a valid path
    trimmed=$(trim_cr "$output")
    [[ -n "$trimmed" ]]
    [[ "$trimmed" == /* ]]
}
register_runtime_test _test_user_home "user identity: HOME is set in container"

#!/usr/bin/env bats

# Tests for BusyBox-based images (Alpine, etc.)
# These images use different utilities: adduser/addgroup instead of useradd/groupadd
# The entrypoint script must detect and handle both code paths

load helpers

setup() {
    TEMP_WORKSPACE=$(mktemp -d)
}

teardown() {
    rm -rf "$TEMP_WORKSPACE"
}

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_busybox_uid() {
    _require_runtime
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$TEMP_WORKSPACE" run --image alpine:latest -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}
register_runtime_test _test_busybox_uid "busybox: user created with correct UID in alpine"

_test_busybox_username() {
    _require_runtime
    host_user=$(whoami)
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$TEMP_WORKSPACE" run --image alpine:latest -- whoami
    [ "$status" -eq 0 ]
    assert_last_line "$host_user"
}
register_runtime_test _test_busybox_username "busybox: username matches host in alpine"

_test_busybox_gid() {
    _require_runtime
    host_gid=$(id -g)
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$TEMP_WORKSPACE" run --image alpine:latest -- id -g
    [ "$status" -eq 0 ]
    assert_last_line "$host_gid"
}
register_runtime_test _test_busybox_gid "busybox: group created with correct GID in alpine"

_test_busybox_ownership() {
    _require_runtime
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$TEMP_WORKSPACE" run --image alpine:latest -- touch testfile.txt
    [ "$status" -eq 0 ]

    [ -f "$TEMP_WORKSPACE/testfile.txt" ]
    file_uid=$(ls -ln "$TEMP_WORKSPACE/testfile.txt" | awk '{print $3}')
    [ "$file_uid" -eq "$host_uid" ]
}
register_runtime_test _test_busybox_ownership "busybox: file ownership preserved in alpine"

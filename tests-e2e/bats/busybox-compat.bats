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

@test "busybox: user created with correct UID in alpine" {
    host_uid=$(id -u)
    run $CTENV --quiet run --image alpine:latest --project-dir "$TEMP_WORKSPACE" -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}

@test "busybox: username matches host in alpine" {
    host_user=$(whoami)
    run $CTENV --quiet run --image alpine:latest --project-dir "$TEMP_WORKSPACE" -- whoami
    [ "$status" -eq 0 ]
    assert_last_line "$host_user"
}

@test "busybox: group created with correct GID in alpine" {
    host_gid=$(id -g)
    run $CTENV --quiet run --image alpine:latest --project-dir "$TEMP_WORKSPACE" -- id -g
    [ "$status" -eq 0 ]
    assert_last_line "$host_gid"
}

@test "busybox: file ownership preserved in alpine" {
    host_uid=$(id -u)
    run $CTENV --quiet run --image alpine:latest --project-dir "$TEMP_WORKSPACE" -- touch testfile.txt
    [ "$status" -eq 0 ]

    [ -f "$TEMP_WORKSPACE/testfile.txt" ]
    file_uid=$(ls -ln "$TEMP_WORKSPACE/testfile.txt" | awk '{print $3}')
    [ "$file_uid" -eq "$host_uid" ]
}

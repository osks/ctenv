#!/usr/bin/env bats

# Tests for user identity preservation - the core ctenv value proposition
# ctenv creates a user inside containers with matching UID/GID to avoid permission issues

load helpers

@test "user identity: container user has same UID as host" {
    cd "$PROJECT1"
    host_uid=$(id -u)
    run $CTENV --quiet run test -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}

@test "user identity: container user has same GID as host" {
    cd "$PROJECT1"
    host_gid=$(id -g)
    run $CTENV --quiet run test -- id -g
    [ "$status" -eq 0 ]
    assert_last_line "$host_gid"
}

@test "user identity: container username matches host" {
    cd "$PROJECT1"
    host_user=$(whoami)
    run $CTENV --quiet run test -- whoami
    [ "$status" -eq 0 ]
    assert_last_line "$host_user"
}

@test "user identity: HOME is set in container" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- sh -c 'echo $HOME'
    [ "$status" -eq 0 ]
    # HOME should be non-empty and a valid path
    trimmed=$(trim_cr "$output")
    [[ -n "$trimmed" ]]
    [[ "$trimmed" == /* ]]
}

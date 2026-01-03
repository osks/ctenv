#!/usr/bin/env bats

# Tests for project directory and project target behavior
# Reference: Project (-p / --project-dir, --project-target)

load helpers

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_project_auto_detected() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_project_auto_detected "project: auto-detected from .ctenv.toml location"

_test_project_target_from_config() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_project_target_from_config "project: project_target from config applied"

_test_project_target_flag() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --project-target /myproject test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/myproject"
}
register_runtime_test _test_project_target_flag "project: --project-target sets target path"

_test_project_dir_flag() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$PROJECT1" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_project_dir_flag "project: --project-dir sets project dir"

_test_project_dir_and_target() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$PROJECT1" run --project-target /custom test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/custom"
}
register_runtime_test _test_project_dir_and_target "project: --project-dir and --project-target together"

_test_project_target_options() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --project-target /repo:ro test -- cat /proc/mounts
    [ "$status" -eq 0 ]
    # Check that /repo mount has 'ro' option
    [[ "$output" == *"/repo"*"ro"* ]]
}
register_runtime_test _test_project_target_options "project: --project-target supports mount options"

# -----------------------------------------------------------------------------
# --no-project-mount tests
# -----------------------------------------------------------------------------

_test_no_project_mount_basic() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "no-proj-mount-$RUNTIME")

    # Start container with --no-project-mount
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" --no-project-mount test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    # Project root should NOT be mounted
    assert_mount_not_exists "$inspect" "/repo"
}
register_runtime_test _test_no_project_mount_basic "project: --no-project-mount skips project mount"

_test_no_project_mount_with_subpath() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "no-proj-subpath-$RUNTIME")

    # Start container with --no-project-mount and explicit subpath
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" --no-project-mount -s ./src test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    # Project root should NOT be mounted, but src subpath should be
    assert_mount_not_exists "$inspect" "/repo"
    assert_mount_exists "$inspect" "/repo/src"
}
register_runtime_test _test_no_project_mount_with_subpath "project: --no-project-mount with subpath mounts only subpath"

_test_no_project_mount_workdir() {
    _require_runtime
    cd "$PROJECT1"
    # Without project mount, workdir should default to /
    run $CTENV --quiet --runtime "$RUNTIME" run --no-project-mount test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/"
}
register_runtime_test _test_no_project_mount_workdir "project: --no-project-mount sets workdir to /"

_test_no_project_mount_with_subpath_workdir() {
    _require_runtime
    cd "$PROJECT1/src"
    # With --no-project-mount and subpath, workdir should be the subpath
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$PROJECT1" run --no-project-mount -s ./src test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo/src"
}
register_runtime_test _test_no_project_mount_with_subpath_workdir "project: --no-project-mount with subpath sets workdir to subpath"

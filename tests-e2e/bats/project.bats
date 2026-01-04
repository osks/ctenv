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
# --no-auto-project-mount tests
# -----------------------------------------------------------------------------

_test_no_auto_project_mount_basic() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "no-proj-mount-$RUNTIME")

    # Start container with --no-auto-project-mount
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" --no-auto-project-mount test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    # Project root should NOT be mounted
    assert_mount_not_exists "$inspect" "/repo"
}
register_runtime_test _test_no_auto_project_mount_basic "project: --no-auto-project-mount skips project mount"

_test_no_auto_project_mount_with_subpath() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "no-proj-subpath-$RUNTIME")

    # Start container with --no-auto-project-mount and explicit subpath
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" --no-auto-project-mount -s ./src test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    # Project root should NOT be mounted, but src subpath should be
    assert_mount_not_exists "$inspect" "/repo"
    assert_mount_exists "$inspect" "/repo/src"
}
register_runtime_test _test_no_auto_project_mount_with_subpath "project: --no-auto-project-mount with subpath mounts only subpath"

_test_no_auto_project_mount_workdir() {
    _require_runtime
    cd "$PROJECT1"
    # Without project mount, workdir still resolves based on cwd position
    # Docker creates the workdir directory, Podman fails if it doesn't exist
    run $CTENV --quiet --runtime "$RUNTIME" run --no-auto-project-mount test -- pwd
    if [ "$RUNTIME" = "docker" ]; then
        [ "$status" -eq 0 ]
        assert_last_line "/repo"
    else
        # Podman fails because --workdir path doesn't exist
        [ "$status" -ne 0 ]
    fi
}
register_runtime_test _test_no_auto_project_mount_workdir "project: --no-auto-project-mount preserves workdir resolution"

_test_no_auto_project_mount_with_subpath_workdir() {
    _require_runtime
    cd "$PROJECT1"
    # With --no-auto-project-mount and subpath, workdir still resolves based on cwd
    # cwd is project root, so workdir is /repo (even though /repo isn't mounted)
    run $CTENV --quiet --runtime "$RUNTIME" run --no-auto-project-mount -s ./src test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_no_auto_project_mount_with_subpath_workdir "project: --no-auto-project-mount with subpath preserves workdir"

# -----------------------------------------------------------------------------
# Workdir auto-resolution tests
# -----------------------------------------------------------------------------

_test_workdir_at_project_root() {
    _require_runtime
    cd "$PROJECT1"
    # At project root, workdir should be project_target
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_workdir_at_project_root "workdir: at project root resolves to project_target"

_test_workdir_in_subdirectory() {
    _require_runtime
    cd "$PROJECT1/src"
    # In subdirectory, workdir should preserve relative position
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo/src"
}
register_runtime_test _test_workdir_in_subdirectory "workdir: in subdirectory preserves relative position"

_test_workdir_in_nested_subdirectory() {
    _require_runtime
    mkdir -p "$PROJECT1/src/nested/deep"
    cd "$PROJECT1/src/nested/deep"
    # In nested subdirectory, workdir should preserve full relative path
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo/src/nested/deep"
}
register_runtime_test _test_workdir_in_nested_subdirectory "workdir: in nested subdirectory preserves full path"

_test_workdir_outside_project() {
    _require_runtime
    local outside_dir=$(mktemp -d)
    cd "$outside_dir"
    # Outside project with explicit --project-dir, workdir should be project_target
    run $CTENV --quiet --runtime "$RUNTIME" --project-dir "$PROJECT1" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
    rmdir "$outside_dir"
}
register_runtime_test _test_workdir_outside_project "workdir: outside project defaults to project_target"

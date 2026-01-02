#!/usr/bin/env bats

# Tests for project directory and project mount behavior
# Reference: Project (-p / --project)

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

_test_project_mount_from_config() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_project_mount_from_config "project: project_mount from config applied"

_test_project_mount_flag() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --project-mount /myproject test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/myproject"
}
register_runtime_test _test_project_mount_flag "project: --project-mount sets mount path"

_test_project_dir_flag() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$PROJECT1" test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}
register_runtime_test _test_project_dir_flag "project: --project-dir sets project dir"

_test_project_dir_and_mount() {
    _require_runtime
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$PROJECT1" --project-mount /custom test -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/custom"
}
register_runtime_test _test_project_dir_and_mount "project: --project-dir and --project-mount together"

_test_project_mount_options() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --project-mount /repo:ro test -- cat /proc/mounts
    [ "$status" -eq 0 ]
    # Check that /repo mount has 'ro' option
    [[ "$output" == *"/repo"*"ro"* ]]
}
register_runtime_test _test_project_mount_options "project: --project-mount supports mount options"

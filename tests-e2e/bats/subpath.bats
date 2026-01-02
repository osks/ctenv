#!/usr/bin/env bats

# Tests for subpath behavior
# Reference: Subpath (-s / --subpath)

load helpers

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_subpath_defaults() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- ls /repo
    [ "$status" -eq 0 ]
    [[ "$output" == *"README.md"* ]]
    [[ "$output" == *"src"* ]]
}
register_runtime_test _test_subpath_defaults "subpath: defaults to project directory"

_test_subpath_single() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --subpath ./src test -- ls /repo/src
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}
register_runtime_test _test_subpath_single "subpath: single subpath limits mount"

_test_subpath_root_not_accessible() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --subpath ./src test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}
register_runtime_test _test_subpath_root_not_accessible "subpath: project root not accessible when subpath specified"

_test_subpath_multiple() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run -s ./src -s ./scripts test -- sh -c "ls /repo/src && ls /repo/scripts"
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
    [[ "$output" == *"build.sh"* ]]
}
register_runtime_test _test_subpath_multiple "subpath: multiple subpaths both accessible"

_test_subpath_multiple_root_not_accessible() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run -s ./src -s ./scripts test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}
register_runtime_test _test_subpath_multiple_root_not_accessible "subpath: project root not accessible with multiple subpaths"

_test_subpath_readonly() {
    _require_runtime
    cd "$PROJECT1"
    # Try to create a file in read-only subpath - should fail
    run $CTENV --quiet --runtime "$RUNTIME" run -s ./scripts::ro test -- touch /repo/scripts/newfile.txt
    [ "$status" -ne 0 ]
}
register_runtime_test _test_subpath_readonly "subpath: read-only option respected"

_test_subpath_mixed_rw_ro() {
    _require_runtime
    cd "$PROJECT1"
    # src is rw, scripts is ro
    run $CTENV --quiet --runtime "$RUNTIME" run -s ./src -s ./scripts::ro test -- sh -c "touch /repo/src/testfile.txt && rm /repo/src/testfile.txt"
    [ "$status" -eq 0 ]
}
register_runtime_test _test_subpath_mixed_rw_ro "subpath: mixed read-write and read-only"

_test_subpath_inspect_volume_options() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "subpath-opts-$RUNTIME")

    # Start container with subpaths: src (rw), scripts (ro)
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" -s ./src -s ./scripts::ro test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    assert_mount_rw "$inspect" "/repo/src"
    assert_mount_ro "$inspect" "/repo/scripts"
}
register_runtime_test _test_subpath_inspect_volume_options "subpath: inspect verifies volume options"

_test_subpath_inspect_root_not_mounted() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "subpath-noproj-$RUNTIME")

    # Start container with only src subpath
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" -s ./src test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    assert_mount_not_exists "$inspect" "/repo"
    assert_mount_exists "$inspect" "/repo/src"
}
register_runtime_test _test_subpath_inspect_root_not_mounted "subpath: inspect verifies project root not mounted"

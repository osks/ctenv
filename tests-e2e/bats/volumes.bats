#!/usr/bin/env bats

# Tests for volume mounting behavior
# Reference: Volume (-v / --volume)

load helpers

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_volume_subpath_relative() {
    _require_runtime
    # Reference: Subpaths of project mounted relative to project target
    # Example: --project-target /repo -v ./src → src at /repo/src
    # Fixture has project_target = "/repo" and src/ subdirectory with sample.txt
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --volume ./src test -- ls /repo/src

    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}
register_runtime_test _test_volume_subpath_relative "volume: subpath mounted relative to project target"

_test_volume_explicit_path() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run --volume "$PROJECT1/src:/data" test -- ls /data

    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}
register_runtime_test _test_volume_explicit_path "volume: explicit container path via volume syntax"

_test_volume_file_accessible() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --quiet --runtime "$RUNTIME" run test -- cat /repo/README.md

    [ "$status" -eq 0 ]
    [[ "$output" == *"fixture"* ]]
}
register_runtime_test _test_volume_file_accessible "volume: file is accessible in container"

_test_volume_multiple_inspect() {
    _require_runtime
    cd "$PROJECT1"
    local cname=$(container_name "volumes-$RUNTIME")

    # Start container with sleep to keep it running
    $CTENV --quiet --runtime "$RUNTIME" run --name "$cname" --volume ./src --volume ./scripts::ro test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$($RUNTIME inspect "$cname")
    $RUNTIME rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    assert_mount_rw "$inspect" "/repo/src"
    assert_mount_ro "$inspect" "/repo/scripts"
}
register_runtime_test _test_volume_multiple_inspect "volume: multiple volumes with inspect verification"

_test_volume_external() {
    _require_runtime
    cd "$PROJECT1"
    local test_dir=$(mktemp -d)
    echo "external content" > "$test_dir/external.txt"

    run $CTENV --quiet --runtime "$RUNTIME" run -v "$test_dir:/external:ro" test -- cat /external/external.txt
    [ "$status" -eq 0 ]
    assert_last_line "external content"

    rm -rf "$test_dir"
}
register_runtime_test _test_volume_external "volume: external volume with explicit container path"

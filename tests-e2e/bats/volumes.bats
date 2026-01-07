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

# Named volume name - clearly identifies it belongs to ctenv tests
NAMED_VOLUME="ctenv-test-named-volume"

# Helper to clean up named volume
_cleanup_named_volume() {
    $RUNTIME volume rm -f "$NAMED_VOLUME" >/dev/null 2>&1 || true
}

_test_named_volume_requires_chown() {
    _require_runtime
    _cleanup_named_volume
    cd "$PROJECT1"

    # Without :chown, writing to named volume fails (root-owned volume, non-root user)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --volume "$NAMED_VOLUME:/test-vol" test -- \
        sh -c "echo 'test' > /test-vol/test.txt"

    _cleanup_named_volume

    # Should fail with permission denied
    [ "$status" -ne 0 ]
    [[ "$output" == *"Permission denied"* ]] || [[ "$output" == *"permission denied"* ]]
}
register_runtime_test _test_named_volume_requires_chown "volume: named volume without chown fails (documents chown purpose)"

_test_named_volume_basic() {
    _require_runtime
    _cleanup_named_volume
    cd "$PROJECT1"

    # Write data to named volume (chown fixes ownership)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --volume "$NAMED_VOLUME:/test-vol:chown" test -- \
        sh -c "echo 'named volume works' > /test-vol/test.txt && cat /test-vol/test.txt"

    _cleanup_named_volume

    [ "$status" -eq 0 ]
    assert_last_line "named volume works"
}
register_runtime_test _test_named_volume_basic "volume: named volume with chown works"

_test_named_volume_persistence() {
    _require_runtime
    _cleanup_named_volume
    cd "$PROJECT1"

    # First run: write data (chown fixes ownership)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --volume "$NAMED_VOLUME:/test-vol:chown" test -- \
        sh -c "echo 'persistent data' > /test-vol/persist.txt"
    [ "$status" -eq 0 ]

    # Second run: read data back (chown not needed for read, but keeps it consistent)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --volume "$NAMED_VOLUME:/test-vol:chown" test -- \
        cat /test-vol/persist.txt

    _cleanup_named_volume

    [ "$status" -eq 0 ]
    assert_last_line "persistent data"
}
register_runtime_test _test_named_volume_persistence "volume: named volume persists data across runs"

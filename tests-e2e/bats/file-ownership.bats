#!/usr/bin/env bats

# Tests for file ownership preservation
# Files created inside containers should be owned by the host user

load helpers

setup() {
    # Create temp directory for file creation tests
    TEMP_WORKSPACE=$(mktemp -d)
}

teardown() {
    rm -rf "$TEMP_WORKSPACE"
}

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_file_ownership_touch() {
    _require_runtime
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" -- touch created_file.txt
    [ "$status" -eq 0 ]

    # Check file was created
    [ -f "$TEMP_WORKSPACE/created_file.txt" ]

    # Check ownership matches host user (ls -ln is portable)
    file_uid=$(ls -ln "$TEMP_WORKSPACE/created_file.txt" | awk '{print $3}')
    [ "$file_uid" -eq "$host_uid" ]
}
register_runtime_test _test_file_ownership_touch "file ownership: created file owned by host user"

_test_file_ownership_content() {
    _require_runtime
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" -- sh -c 'echo "test content" > output.txt'
    [ "$status" -eq 0 ]

    # Check file exists and has content
    [ -f "$TEMP_WORKSPACE/output.txt" ]
    [[ "$(cat "$TEMP_WORKSPACE/output.txt")" == "test content" ]]

    # Check ownership (ls -ln is portable)
    file_uid=$(ls -ln "$TEMP_WORKSPACE/output.txt" | awk '{print $3}')
    [ "$file_uid" -eq "$host_uid" ]
}
register_runtime_test _test_file_ownership_content "file ownership: file with content owned by host user"

_test_file_ownership_directory() {
    _require_runtime
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" run --project-dir "$TEMP_WORKSPACE" -- mkdir subdir
    [ "$status" -eq 0 ]

    # Check directory was created with correct ownership
    [ -d "$TEMP_WORKSPACE/subdir" ]
    dir_uid=$(ls -ldn "$TEMP_WORKSPACE/subdir" | awk '{print $3}')
    [ "$dir_uid" -eq "$host_uid" ]
}
register_runtime_test _test_file_ownership_directory "file ownership: directory created owned by host user"

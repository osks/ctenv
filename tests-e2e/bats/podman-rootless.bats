#!/usr/bin/env bats

# Tests for ctenv with --runtime podman (rootless mode)
# These tests verify ctenv works correctly with podman's --userns=keep-id.

load helpers

setup() {
    command -v podman >/dev/null || skip "podman not available"
    # Check if running rootless
    if ! podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -q true; then
        skip "podman is not running in rootless mode"
    fi
    # Check if subuid/subgid are configured (required for rootless)
    if ! grep -q "^$(whoami):" /etc/subuid 2>/dev/null; then
        skip "subuid not configured for $(whoami)"
    fi
    if ! grep -q "^$(whoami):" /etc/subgid 2>/dev/null; then
        skip "subgid not configured for $(whoami)"
    fi
}

# Common ctenv command for podman
CTENV_PODMAN="$CTENV -v --runtime podman"

# -----------------------------------------------------------------------------
# Basic Functionality
# -----------------------------------------------------------------------------

@test "ctenv podman: runs command in container" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine -- echo "hello from ctenv"
    [ "$status" -eq 0 ]
    [[ "$output" == *"hello from ctenv"* ]]
}

@test "ctenv podman: project mounted at /repo" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine -- pwd
    [ "$status" -eq 0 ]
    assert_last_line "/repo"
}

@test "ctenv podman: can read project files" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine -- cat /repo/README.md
    [ "$status" -eq 0 ]
    [[ "$output" == *"project1"* ]] || [[ "$output" == *"Test"* ]]
}

# -----------------------------------------------------------------------------
# User Identity Tests - core ctenv value proposition
# -----------------------------------------------------------------------------

@test "ctenv podman: UID preserved" {
    cd "$PROJECT1"
    host_uid=$(id -u)
    run $CTENV_PODMAN run --image alpine -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}

@test "ctenv podman: GID preserved" {
    cd "$PROJECT1"
    host_gid=$(id -g)
    run $CTENV_PODMAN run --image alpine -- id -g
    [ "$status" -eq 0 ]
    assert_last_line "$host_gid"
}

@test "ctenv podman: username exists in container" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine -- whoami
    [ "$status" -eq 0 ]
    # Should not be "root"
    [[ "$(trim_cr "$output")" != "root" ]]
}

@test "ctenv podman: HOME is set" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine -- sh -c 'echo $HOME'
    [ "$status" -eq 0 ]
    # HOME should be non-empty
    [[ -n "$(trim_cr "$output")" ]]
}

# -----------------------------------------------------------------------------
# File Ownership Tests
# -----------------------------------------------------------------------------

@test "ctenv podman: files created have host UID" {
    cd "$PROJECT1"
    local test_file="test-podman-$$"

    run $CTENV_PODMAN run --image alpine -- touch "/repo/$test_file"
    [ "$status" -eq 0 ]

    # Check ownership on host
    file_uid=$(stat -c %u "$PROJECT1/$test_file" 2>/dev/null || stat -f %u "$PROJECT1/$test_file")
    [ "$file_uid" -eq "$(id -u)" ]

    rm -f "$PROJECT1/$test_file"
}

@test "ctenv podman: files created have host GID" {
    cd "$PROJECT1"
    local test_file="test-podman-gid-$$"

    run $CTENV_PODMAN run --image alpine -- touch "/repo/$test_file"
    [ "$status" -eq 0 ]

    # Check ownership on host
    file_gid=$(stat -c %g "$PROJECT1/$test_file" 2>/dev/null || stat -f %g "$PROJECT1/$test_file")
    [ "$file_gid" -eq "$(id -g)" ]

    rm -f "$PROJECT1/$test_file"
}

@test "ctenv podman: can write file with content" {
    cd "$PROJECT1"
    local test_file="test-podman-content-$$"

    run $CTENV_PODMAN run --image alpine -- sh -c "echo 'hello podman' > /repo/$test_file"
    [ "$status" -eq 0 ]

    [ -f "$PROJECT1/$test_file" ]
    [ "$(cat "$PROJECT1/$test_file")" = "hello podman" ]

    rm -f "$PROJECT1/$test_file"
}

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------

@test "ctenv podman: environment variables passed through" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine --env TEST_VAR=hello -- sh -c 'echo $TEST_VAR'
    [ "$status" -eq 0 ]
    assert_last_line "hello"
}

@test "ctenv podman: multiple environment variables" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine --env VAR1=one --env VAR2=two -- sh -c 'echo $VAR1-$VAR2'
    [ "$status" -eq 0 ]
    assert_last_line "one-two"
}

# -----------------------------------------------------------------------------
# Volume Mounts
# -----------------------------------------------------------------------------

@test "ctenv podman: additional volume mount" {
    cd "$PROJECT1"
    local test_dir=$(mktemp -d)
    echo "extra" > "$test_dir/extra.txt"

    run $CTENV_PODMAN run --image alpine -v "$test_dir:/extra:ro" -- cat /extra/extra.txt
    [ "$status" -eq 0 ]
    assert_last_line "extra"

    rm -rf "$test_dir"
}

# -----------------------------------------------------------------------------
# Subpath Tests
# -----------------------------------------------------------------------------

@test "ctenv podman: subpath mount" {
    cd "$PROJECT1"
    mkdir -p "$PROJECT1/subdir"
    echo "subdir content" > "$PROJECT1/subdir/file.txt"

    # Subpaths mount relative to project_mount (/repo), so subdir -> /repo/subdir
    run $CTENV_PODMAN run --image alpine --subpath subdir -- cat /repo/subdir/file.txt
    [ "$status" -eq 0 ]
    assert_last_line "subdir content"

    rm -rf "$PROJECT1/subdir"
}

# -----------------------------------------------------------------------------
# Dry Run
# -----------------------------------------------------------------------------

@test "ctenv podman: dry-run shows podman command" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine --dry-run -- echo test
    [ "$status" -eq 0 ]
    # Should show podman command, not docker
    [[ "$output" == *"podman run"* ]]
    # Should include --userns=keep-id
    [[ "$output" == *"--userns=keep-id"* ]]
}

# -----------------------------------------------------------------------------
# Post-start Commands
# -----------------------------------------------------------------------------

@test "ctenv podman: post-start command runs" {
    cd "$PROJECT1"
    run $CTENV_PODMAN run --image alpine --post-start-command "echo setup-done" -- echo "main"
    [ "$status" -eq 0 ]
    [[ "$output" == *"setup-done"* ]]
    [[ "$output" == *"main"* ]]
}

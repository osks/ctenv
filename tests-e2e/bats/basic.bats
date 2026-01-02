#!/usr/bin/env bats

load helpers

# -----------------------------------------------------------------------------
# Non-parameterized tests (don't require container runtime)
# -----------------------------------------------------------------------------

@test "ctenv --help shows usage" {
    run $CTENV --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"run"* ]]
}

@test "ctenv --version works" {
    run $CTENV --version
    [ "$status" -eq 0 ]
}

# -----------------------------------------------------------------------------
# Parameterized tests (run with both docker and podman)
# -----------------------------------------------------------------------------

_test_starts_container() {
    _require_runtime
    cd "$PROJECT1"

    # Start container with sleep to keep it running
    $CTENV --quiet --runtime "$RUNTIME" run test -- sleep 60 &
    CTENV_PID=$!

    # Wait for container to start (may need to pull image)
    container_id=""
    for i in {1..30}; do
        container_id=$($RUNTIME ps --filter "label=se.osd.ctenv.managed=true" --format '{{.ID}}' | head -1)
        [ -n "$container_id" ] && break
        sleep 1
    done

    # Verify container is running
    [ -n "$container_id" ]

    # Inspect container to verify it's a real container
    run $RUNTIME inspect "$container_id" --format '{{.State.Running}}'
    [ "$status" -eq 0 ]
    [ "$output" = "true" ]

    # Verify it's using the expected image
    run $RUNTIME inspect "$container_id" --format '{{.Config.Image}}'
    [ "$status" -eq 0 ]
    [[ "$output" == *"ubuntu"* ]]

    # Clean up: stop the container
    $RUNTIME stop "$container_id" >/dev/null 2>&1 || true
    $RUNTIME rm -f "$container_id" >/dev/null 2>&1 || true
    kill $CTENV_PID 2>/dev/null || true
    wait $CTENV_PID 2>/dev/null || true
}
register_runtime_test _test_starts_container "ctenv run starts a real container"

_test_dry_run() {
    _require_runtime
    cd "$PROJECT1"
    run $CTENV --runtime "$RUNTIME" run --dry-run test -- echo test
    [ "$status" -eq 0 ]
    # Should show correct runtime command
    [[ "$output" == *"$RUNTIME run"* ]]
    # Podman-specific: should include --userns=keep-id
    if [[ "$RUNTIME" == "podman" ]]; then
        [[ "$output" == *"--userns=keep-id"* ]]
    fi
}
register_runtime_test _test_dry_run "dry-run shows correct runtime command"


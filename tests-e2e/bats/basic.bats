#!/usr/bin/env bats

load helpers

@test "ctenv --help shows usage" {
    run $CTENV --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"run"* ]]
}

@test "ctenv --version works" {
    run $CTENV --version
    [ "$status" -eq 0 ]
}

@test "ctenv run starts a real docker container" {
    cd "$PROJECT1"

    # Start container with sleep to keep it running
    $CTENV --quiet run test -- sleep 60 &
    CTENV_PID=$!

    # Wait for container to start (may need to pull image)
    container_id=""
    for i in {1..30}; do
        container_id=$(docker ps --filter "label=se.osd.ctenv.managed=true" --format '{{.ID}}' | head -1)
        [ -n "$container_id" ] && break
        sleep 1
    done

    # Verify container is running
    [ -n "$container_id" ]

    # Inspect container to verify it's a real docker container
    run docker inspect "$container_id" --format '{{.State.Running}}'
    [ "$status" -eq 0 ]
    [ "$output" = "true" ]

    # Verify it's using the expected image
    run docker inspect "$container_id" --format '{{.Config.Image}}'
    [ "$status" -eq 0 ]
    [[ "$output" == *"ubuntu"* ]]

    # Clean up: stop the container
    docker stop "$container_id" >/dev/null 2>&1 || true
    docker rm -f "$container_id" >/dev/null 2>&1 || true
    kill $CTENV_PID 2>/dev/null || true
    wait $CTENV_PID 2>/dev/null || true
}


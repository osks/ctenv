#!/usr/bin/env bats

# Tests for volume mounting behavior
# Reference: Volume (-v / --volume)

load helpers

@test "volume: subpath mounted relative to project mount" {
    # Reference: Subpaths of project mounted relative to project mount
    # Example: -m /repo -v ./src → src at /repo/src
    # Fixture has project_mount = "/repo" and src/ subdirectory with sample.txt
    cd "$PROJECT1"
    run $CTENV --quiet run --volume ./src test -- ls /repo/src

    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}

@test "volume: explicit container path via volume syntax" {
    cd "$PROJECT1"
    run $CTENV --quiet run --volume "$PROJECT1/src:/data" test -- ls /data

    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}

@test "volume: file is accessible in container" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- cat /repo/README.md

    [ "$status" -eq 0 ]
    [[ "$output" == *"fixture"* ]]
}

@test "volume: multiple volumes with docker inspect verification" {
    cd "$PROJECT1"
    local cname=$(container_name "volumes")

    # Start container with sleep to keep it running
    $CTENV --quiet run --name "$cname" --volume ./src --volume ./scripts::ro test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    # Inspect mounts
    local mounts
    mounts=$(docker inspect "$cname" --format '{{json .Mounts}}')

    # Cleanup
    docker rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    # Verify src volume exists and is read-write
    local src_rw
    src_rw=$(echo "$mounts" | jq -r '.[] | select(.Destination == "/repo/src") | .RW')
    [ "$src_rw" = "true" ]

    # Verify scripts volume exists and is read-only
    local scripts_rw
    scripts_rw=$(echo "$mounts" | jq -r '.[] | select(.Destination == "/repo/scripts") | .RW')
    [ "$scripts_rw" = "false" ]
}

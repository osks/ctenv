#!/usr/bin/env bats

# Tests for subpath behavior
# Reference: Subpath (-s / --subpath)

load helpers

@test "subpath: defaults to project directory when not specified" {
    cd "$PROJECT1"
    run $CTENV --quiet run test -- ls /repo
    [ "$status" -eq 0 ]
    [[ "$output" == *"README.md"* ]]
    [[ "$output" == *"src"* ]]
}

@test "subpath: single subpath limits mount" {
    cd "$PROJECT1"
    run $CTENV --quiet run --subpath ./src test -- ls /repo/src
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
}

@test "subpath: project root not accessible when subpath specified" {
    cd "$PROJECT1"
    run $CTENV --quiet run --subpath ./src test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}

@test "subpath: multiple subpaths both accessible" {
    cd "$PROJECT1"
    run $CTENV --quiet run -s ./src -s ./scripts test -- sh -c "ls /repo/src && ls /repo/scripts"
    [ "$status" -eq 0 ]
    [[ "$output" == *"sample.txt"* ]]
    [[ "$output" == *"build.sh"* ]]
}

@test "subpath: project root not accessible with multiple subpaths" {
    cd "$PROJECT1"
    run $CTENV --quiet run -s ./src -s ./scripts test -- cat /repo/README.md
    [ "$status" -ne 0 ]
}

@test "subpath: read-only option respected" {
    cd "$PROJECT1"
    # Try to create a file in read-only subpath - should fail
    run $CTENV --quiet run -s ./scripts::ro test -- touch /repo/scripts/newfile.txt
    [ "$status" -ne 0 ]
}

@test "subpath: mixed read-write and read-only" {
    cd "$PROJECT1"
    # src is rw, scripts is ro
    run $CTENV --quiet run -s ./src -s ./scripts::ro test -- sh -c "touch /repo/src/testfile.txt && rm /repo/src/testfile.txt"
    [ "$status" -eq 0 ]
}

@test "subpath: docker inspect verifies volume options" {
    cd "$PROJECT1"
    local cname=$(container_name "subpath-opts")

    # Start container with subpaths: src (rw), scripts (ro)
    $CTENV --quiet run --name "$cname" -s ./src -s ./scripts::ro test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$(docker inspect "$cname")
    docker rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    assert_mount_rw "$inspect" "/repo/src"
    assert_mount_ro "$inspect" "/repo/scripts"
}

@test "subpath: docker inspect verifies project root not mounted" {
    cd "$PROJECT1"
    local cname=$(container_name "subpath-noproj")

    # Start container with only src subpath
    $CTENV --quiet run --name "$cname" -s ./src test -- sleep 30 &
    local ctenv_pid=$!
    sleep 2  # Wait for container to start

    local inspect=$(docker inspect "$cname")
    docker rm -f "$cname" >/dev/null 2>&1 || true
    wait $ctenv_pid 2>/dev/null || true

    assert_mount_not_exists "$inspect" "/repo"
    assert_mount_exists "$inspect" "/repo/src"
}

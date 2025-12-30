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

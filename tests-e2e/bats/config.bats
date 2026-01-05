#!/usr/bin/env bats

# Tests for config command
# Introspection of effective configuration

load helpers

setup() {
    TEMP_WORKSPACE=$(mktemp -d)
}

teardown() {
    rm -rf "$TEMP_WORKSPACE"
}

@test "config: shows default image" {
    cd "$TEMP_WORKSPACE"
    run $CTENV config
    [ "$status" -eq 0 ]
    [[ "$output" == *"ubuntu"* ]]
}

@test "config: shows default command" {
    cd "$TEMP_WORKSPACE"
    run $CTENV config
    [ "$status" -eq 0 ]
    [[ "$output" == *"bash"* ]]
}

@test "config: shows containers from project config" {
    cd "$PROJECT1"
    run $CTENV config
    [ "$status" -eq 0 ]
    # Fixture has 'test' and 'alpine' containers
    [[ "$output" == *"test"* ]]
    [[ "$output" == *"alpine"* ]]
}

@test "config: config show is alias for config" {
    cd "$PROJECT1"
    run $CTENV config show
    [ "$status" -eq 0 ]
    [[ "$output" == *"test"* ]]
}

@test "config: shows image from project config" {
    cd "$PROJECT1"
    run $CTENV config
    [ "$status" -eq 0 ]
    # Fixture has ubuntu:22.04 for test container
    [[ "$output" == *"ubuntu:22.04"* ]]
}

@test "config: default=true uses specified container when no container arg provided" {
    cd "$TEMP_WORKSPACE"

    # Create config with default container
    cat > .ctenv.toml << 'EOF'
[containers.mydev]
image = "alpine:latest"
command = "echo from-default-container"
default = true
EOF

    # Run without specifying container - should use mydev
    run $CTENV run --dry-run
    [ "$status" -eq 0 ]
    [[ "$output" == *"alpine:latest"* ]]
}

@test "config: explicit container arg overrides default=true" {
    cd "$TEMP_WORKSPACE"

    # Create config with default container and another container
    cat > .ctenv.toml << 'EOF'
[containers.mydev]
image = "alpine:latest"
default = true

[containers.other]
image = "ubuntu:22.04"
EOF

    # Run with explicit container - should use 'other', not 'mydev'
    run $CTENV run --dry-run other
    [ "$status" -eq 0 ]
    [[ "$output" == *"ubuntu:22.04"* ]]
}

@test "config: multiple containers with default=true gives error" {
    cd "$MULTIPLE_DEFAULTS"

    # Should fail because multiple containers are marked as default
    run $CTENV run --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"Multiple containers marked as default"* ]]
}

#!/usr/bin/env bats

# Determine project root from test file location
BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"

# Use project's ctenv, not global tool
CTENV="uv run --project $PROJECT_ROOT python -m ctenv"

@test "ctenv --help shows usage" {
    run $CTENV --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"run"* ]]
}

@test "ctenv run --dry-run basic" {
    run $CTENV run --dry-run -- echo hello
    [ "$status" -eq 0 ]
    [[ "$output" == *"[ctenv] run"* ]]
}

@test "workspace: project_mount from config applied" {
    # Create temp workspace with config
    tmpdir=$(mktemp -d)
    cat > "$tmpdir/.ctenv.toml" <<EOF
[defaults]
project_mount = "/repo"

[containers.test]
image = "ubuntu:22.04"
EOF
    mkdir -p "$tmpdir/src"

    cd "$tmpdir"
    run $CTENV --verbose run --dry-run test -- pwd

    rm -rf "$tmpdir"

    [ "$status" -eq 0 ]
    [[ "$output" == *":/repo:z"* ]]
    [[ "$output" == *"--workdir=/repo"* ]]
}

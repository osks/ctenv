#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIMA_VM_NAME="ctenv-test"
LIMA_CONFIG="$SCRIPT_DIR/lima.yaml"

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [args...]

Run commands in the ctenv Lima VM.

Commands:
    run <cmd>   Run a command in the VM
    setup       Create/start Lima VM
    status      Show VM status
    sync        Sync files to VM
    down        Stop and delete Lima VM
    help        Show this help

Examples:
    $(basename "$0") run bats tests-e2e/
    $(basename "$0") run make test
    $(basename "$0") run uv run pytest
    $(basename "$0") setup
    $(basename "$0") status
    $(basename "$0") down
EOF
}

FRESH_VM=false

lima_setup() {
    if limactl list --quiet 2>/dev/null | grep -q "^${LIMA_VM_NAME}$"; then
        if ! limactl list --format json 2>/dev/null | grep -q '"status":"Running"'; then
            echo "Starting VM..."
            limactl start --tty=false "$LIMA_VM_NAME"
        else
            echo "VM already running"
        fi
    else
        echo "Creating Lima VM '$LIMA_VM_NAME'..."
        local vm_type_flag=""
        if [[ "$(uname -s)" == "Darwin" ]]; then
            vm_type_flag="--vm-type=vz"
        fi
        limactl start --tty=false $vm_type_flag --name="$LIMA_VM_NAME" "$LIMA_CONFIG"
        FRESH_VM=true
    fi
}

lima_down() {
    if limactl list --quiet 2>/dev/null | grep -q "^${LIMA_VM_NAME}$"; then
        echo "Stopping and deleting Lima VM '$LIMA_VM_NAME'..."
        limactl stop "$LIMA_VM_NAME" 2>/dev/null || true
        limactl delete "$LIMA_VM_NAME"
    else
        echo "Lima VM '$LIMA_VM_NAME' does not exist"
    fi
}

lima_status() {
    if limactl list --quiet 2>/dev/null | grep -q "^${LIMA_VM_NAME}$"; then
        limactl list | grep -E "^NAME|^${LIMA_VM_NAME}"
    else
        echo "Lima VM '$LIMA_VM_NAME' does not exist"
    fi
}

sync_code() {
    echo "Syncing code to Lima VM..."

    local workspace="/workspace"

    # Ensure workspace exists
    limactl shell --tty=false --workdir / "$LIMA_VM_NAME" -- sudo mkdir -p "$workspace"
    limactl shell --tty=false --workdir / "$LIMA_VM_NAME" -- bash -c "sudo chown \$(id -u):\$(id -g) $workspace"

    # Sync files, excluding .venv to preserve cached dependencies
    tar --no-xattrs --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' -C "$PROJECT_ROOT" -cf - . | \
        limactl shell --tty=false --workdir / "$LIMA_VM_NAME" -- tar -C "$workspace" -xf -
}

sync_deps() {
    echo "Syncing dependencies..."
    limactl shell --tty=false --workdir /workspace "$LIMA_VM_NAME" -- bash -c "export PATH=~/.local/bin:\$PATH && uv sync --all-extras"
}

sync_full() {
    sync_code
    sync_deps
}

run_in_lima() {
    echo "Running in Lima VM: $*"
    limactl shell --tty=false --workdir /workspace "$LIMA_VM_NAME" -- bash -c "export PATH=~/.local/bin:\$PATH && $*"
}

# Parse command
if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

case $1 in
    setup)
        lima_setup
        sync_full
        echo "Lima VM '$LIMA_VM_NAME' is ready"
        ;;
    status)
        lima_status
        ;;
    sync)
        lima_setup
        sync_full
        echo "Files and dependencies synced"
        ;;
    down)
        lima_down
        ;;
    help|-h|--help)
        usage
        ;;
    run)
        shift
        if [[ $# -eq 0 ]]; then
            echo "Error: 'run' requires a command"
            exit 1
        fi
        lima_setup
        if [[ "$FRESH_VM" == true ]]; then
            sync_full
        else
            sync_code
        fi
        run_in_lima "$@"
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac

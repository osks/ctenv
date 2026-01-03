#!/usr/bin/env bats

# Tests for building images with ctenv build command and run --build-dockerfile option

load helpers

# -----------------------------------------------------------------------------
# ctenv build command tests (parameterized for docker/podman)
# -----------------------------------------------------------------------------

_test_ctenv_build_basic() {
    _require_runtime
    cd "$PROJECT1"

    local tag="ctenv-test-build-$$"

    # Build image using ctenv build command
    run $CTENV --runtime "$RUNTIME" build \
        --build-dockerfile Dockerfile.nonroot \
        --build-tag "$tag" \
        test
    [ "$status" -eq 0 ]

    # Verify image was created
    run $RUNTIME image inspect "$tag"
    [ "$status" -eq 0 ]

    # Cleanup
    $RUNTIME rmi "$tag" >/dev/null 2>&1 || true
}
register_runtime_test _test_ctenv_build_basic "ctenv build: builds image from Dockerfile"

_test_ctenv_build_with_context() {
    _require_runtime
    cd "$PROJECT1"

    local tag="ctenv-test-build-ctx-$$"

    # Build with explicit context directory
    run $CTENV --runtime "$RUNTIME" build \
        --build-dockerfile Dockerfile.nonroot \
        --build-context . \
        --build-tag "$tag" \
        test
    [ "$status" -eq 0 ]

    # Verify image was created
    run $RUNTIME image inspect "$tag"
    [ "$status" -eq 0 ]

    # Cleanup
    $RUNTIME rmi "$tag" >/dev/null 2>&1 || true
}
register_runtime_test _test_ctenv_build_with_context "ctenv build: builds with explicit context"

_test_ctenv_build_inline_dockerfile() {
    _require_runtime
    cd "$PROJECT1"

    local tag="ctenv-test-build-inline-$$"

    # Build with inline dockerfile content
    run $CTENV --runtime "$RUNTIME" build \
        --build-dockerfile-content "FROM alpine:latest\nRUN echo hello" \
        --build-tag "$tag" \
        test
    [ "$status" -eq 0 ]

    # Verify image was created
    run $RUNTIME image inspect "$tag"
    [ "$status" -eq 0 ]

    # Cleanup
    $RUNTIME rmi "$tag" >/dev/null 2>&1 || true
}
register_runtime_test _test_ctenv_build_inline_dockerfile "ctenv build: builds with inline Dockerfile content"

_test_ctenv_build_with_args() {
    _require_runtime
    cd "$PROJECT1"

    local tag="ctenv-test-build-args-$$"

    # Build with build args using inline dockerfile that uses ARG
    run $CTENV --runtime "$RUNTIME" build \
        --build-dockerfile-content "FROM alpine:latest\nARG TEST_VAR=default\nRUN echo \$TEST_VAR > /test.txt" \
        --build-arg TEST_VAR=custom_value \
        --build-tag "$tag" \
        test
    [ "$status" -eq 0 ]

    # Verify image was created
    run $RUNTIME image inspect "$tag"
    [ "$status" -eq 0 ]

    # Cleanup
    $RUNTIME rmi "$tag" >/dev/null 2>&1 || true
}
register_runtime_test _test_ctenv_build_with_args "ctenv build: passes build arguments"

# -----------------------------------------------------------------------------
# ctenv run --build-dockerfile tests (parameterized for docker/podman)
# -----------------------------------------------------------------------------

_test_build_dockerfile() {
    _require_runtime
    cd "$PROJECT1"

    # Build and run with the nonroot Dockerfile
    run $CTENV -v --runtime "$RUNTIME" run \
        --build-dockerfile Dockerfile.nonroot \
        test -- echo "build success"
    [ "$status" -eq 0 ]
    assert_last_line "build success"
}
register_runtime_test _test_build_dockerfile "run --build: can build and run from custom Dockerfile"

_test_build_nonroot_user_identity() {
    _require_runtime
    cd "$PROJECT1"

    # Even with a Dockerfile that sets USER appuser, ctenv should preserve host UID
    host_uid=$(id -u)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --build-dockerfile Dockerfile.nonroot \
        test -- id -u
    [ "$status" -eq 0 ]
    assert_last_line "$host_uid"
}
register_runtime_test _test_build_nonroot_user_identity "run --build: user identity preserved with nonroot Dockerfile"

_test_build_nonroot_user_name() {
    _require_runtime
    cd "$PROJECT1"

    # Username should match host user, not the Dockerfile's USER
    host_user=$(whoami)
    run $CTENV --quiet --runtime "$RUNTIME" run \
        --build-dockerfile Dockerfile.nonroot \
        test -- whoami
    [ "$status" -eq 0 ]
    assert_last_line "$host_user"
}
register_runtime_test _test_build_nonroot_user_name "run --build: username matches host with nonroot Dockerfile"

_test_build_dry_run() {
    _require_runtime
    cd "$PROJECT1"

    run $CTENV --runtime "$RUNTIME" run \
        --build-dockerfile Dockerfile.nonroot \
        --dry-run \
        test -- echo test
    [ "$status" -eq 0 ]
    # Should show that it will build an image
    [[ "$output" == *"$RUNTIME"* ]]
}
register_runtime_test _test_build_dry_run "run --build: dry-run works with custom Dockerfile"

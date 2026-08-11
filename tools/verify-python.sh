#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
expected_python=$(tr -d '[:space:]' < "$repo_root/.python-version")
expected_uv="0.11.13"

if ! command -v uv >/dev/null 2>&1; then
    printf 'uv is required to verify the Python workspace.\n' >&2
    exit 1
fi

actual_uv=$(uv --version | awk '{print $2}')
if [ "$actual_uv" != "$expected_uv" ]; then
    printf 'Expected uv %s, found %s.\n' "$expected_uv" "$actual_uv" >&2
    exit 1
fi

cd "$repo_root"
uv sync --frozen --all-packages

actual_python=$(uv run --frozen --all-packages python -c 'import platform; print(platform.python_version())')
if [ "$actual_python" != "$expected_python" ]; then
    printf 'Expected Python %s from .python-version, found %s.\n' "$expected_python" "$actual_python" >&2
    exit 1
fi

uv run --frozen --all-packages ruff format --check \
    services/assistant-runtime \
    services/batch-worker
uv run --frozen --all-packages ruff check \
    services/assistant-runtime \
    services/batch-worker
uv run --frozen --all-packages mypy \
    services/assistant-runtime/src \
    services/assistant-runtime/tests \
    services/batch-worker/src \
    services/batch-worker/tests
uv run --frozen --all-packages pytest

printf 'Python workspace verification passed.\n'
